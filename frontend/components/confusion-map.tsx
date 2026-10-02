import type { ConfusionBucket, ConfusionMap as ConfusionMapData, SkipItem } from "@/lib/types";
import { categoryLabel, cn, plural } from "@/lib/utils";
import { EmptyState } from "./empty-state";
import { SectionHeader } from "./section-header";

const GROUPS = {
  start: {
    title: "Start here",
    hint: "Short, simple files that are safe to open first.",
    bar: "bg-teal",
    soft: "bg-teal-soft",
    text: "text-teal",
  },
  after: {
    title: "Read after basics",
    hint: "Worth reading once you know the entry point and main flow.",
    bar: "bg-amber",
    soft: "bg-amber-soft",
    text: "text-amber",
  },
  skip: {
    title: "Skip initially",
    hint: "Harder or less central. Come back to these later.",
    bar: "bg-rose",
    soft: "bg-rose-soft",
    text: "text-rose",
  },
} as const;

type GroupStyle = (typeof GROUPS)[keyof typeof GROUPS];

function plainReason(reasons: string[]): string {
  return reasons.slice(0, 2).join("; ");
}

export function ConfusionMap({ map, skip }: { map: ConfusionMapData; skip: SkipItem[] }) {
  const total = map.start_here.total + map.read_after_basics.total + map.leave_for_later.total;
  return (
    <div className="space-y-8">
      <SectionHeader
        id="section-confusion-map"
        title="Confusion Map"
        description="Every analysed file, grouped by how hard it is for a newcomer to read. Difficulty is a RepoLens heuristic, not a measurement."
      />
      {total === 0 && skip.length === 0 ? (
        <EmptyState title="Nothing to map">RepoLens did not find enough analysed files to group.</EmptyState>
      ) : (
        <div className="grid gap-6 lg:grid-cols-3">
          <Group style={GROUPS.start} bucket={map.start_here} />
          <Group style={GROUPS.after} bucket={map.read_after_basics} />
          <Group style={GROUPS.skip} bucket={map.leave_for_later} skip={skip} />
        </div>
      )}
    </div>
  );
}

function Group({ style, bucket, skip = [] }: { style: GroupStyle; bucket: ConfusionBucket; skip?: SkipItem[] }) {
  const hidden = bucket.total - bucket.items.length;
  const headingId = `group-${style.title.toLowerCase().replace(/\s+/g, "-")}`;
  return (
    <section aria-labelledby={headingId} className="min-w-0 overflow-hidden rounded-[12px] border border-line">
      <div className={cn("h-0.5", style.bar)} aria-hidden="true" />
      <div className={cn("px-4 py-3.5", style.soft)}>
        <div className="flex items-baseline justify-between gap-2">
          <h3 id={headingId} className={cn("text-[14px] font-semibold", style.text)}>
            {style.title}
          </h3>
          <span className="font-mono text-[12px] text-muted tabular-nums">{bucket.total}</span>
        </div>
        <p className="mt-0.5 text-[12.5px] text-muted">{style.hint}</p>
      </div>
      {bucket.items.length === 0 && skip.length === 0 ? (
        <p className="px-4 py-4 text-[13px] text-faint">No files in this group.</p>
      ) : (
        <ul className="divide-y divide-line">
          {bucket.items.map((item) => (
            <li key={item.path} className="px-4 py-3">
              <p className="font-mono text-[13px] break-all text-fg">{item.path}</p>
              <p className="mt-0.5 text-[12.5px] text-faint">
                {categoryLabel(item.category)} · difficulty {item.difficulty}/100
              </p>
              {item.reasons.length > 0 && <p className="mt-1 text-[13px] text-muted">{plainReason(item.reasons)}</p>}
            </li>
          ))}
          {hidden > 0 && (
            <li className="px-4 py-2.5 text-[12.5px] text-faint">+ {plural(hidden, "less important file")}</li>
          )}
          {skip.length > 0 && (
            <li className="px-4 pt-4 pb-1">
              <p className="text-[11px] font-medium tracking-[0.08em] text-faint uppercase">Folders and tooling</p>
            </li>
          )}
          {skip.map((item) => (
            <li key={item.path} className="px-4 py-3">
              <p className="font-mono text-[13px] break-all text-fg">
                {item.path}
                {item.path.endsWith("/") && item.file_count > 1 && (
                  <span className="ml-2 font-sans text-[12px] text-faint">{plural(item.file_count, "file")}</span>
                )}
              </p>
              <p className="mt-1 text-[13px] text-muted">{item.reason}</p>
            </li>
          ))}
        </ul>
      )}
    </section>
  );
}

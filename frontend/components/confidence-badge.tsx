import { cn } from "@/lib/utils";

const STYLES: Record<string, { dot: string; text: string }> = {
  High: { dot: "bg-teal", text: "text-teal" },
  Medium: { dot: "bg-amber", text: "text-amber" },
  Low: { dot: "bg-rose", text: "text-rose" },
};
const NONE = { dot: "bg-faint", text: "text-muted" };

/** Confidence is always spelled out; colour is only a secondary cue. */
export function ConfidenceBadge({ level, prefix = "Confidence" }: { level: string; prefix?: string }) {
  const style = STYLES[level] ?? NONE;
  const label = level === "No reliable answer" ? level : `${prefix}: ${level}`;
  return (
    <span
      className={cn(
        "inline-flex items-center gap-1.5 rounded-md border border-line bg-raised px-2 py-0.5 text-xs font-medium",
        style.text,
      )}
    >
      <span aria-hidden="true" className={cn("size-1.5 rounded-full", style.dot)} />
      {label}
    </span>
  );
}

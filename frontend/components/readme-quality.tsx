import type { ReadmeCheck, ReadmeQuality as ReadmeQualityData } from "@/lib/types";
import { cn } from "@/lib/utils";
import { EmptyState } from "./empty-state";
import { InlineText } from "./inline-text";
import { Eyebrow, SectionHeader } from "./section-header";

function missingLabel(check: ReadmeCheck): string {
  return check.label.replace(/ found$/, "").replace(/ is referenced$/, "").replace(/ is described$/, "");
}

function scoreTone(score: number): string {
  if (score >= 60) return "bg-teal";
  if (score >= 40) return "bg-amber";
  return "bg-rose";
}

export function ReadmeQuality({ quality }: { quality: ReadmeQualityData | null }) {
  return (
    <div className="space-y-8">
      <SectionHeader
        id="section-readme"
        title="README Review"
        description="How well the README helps a newcomer understand, install, run, test and contribute."
      />
      {quality ? (
        <Report quality={quality} />
      ) : (
        <EmptyState title="README could not be reviewed">RepoLens could not evaluate a README for this repository.</EmptyState>
      )}
    </div>
  );
}

function Report({ quality }: { quality: ReadmeQualityData }) {
  const strengths = quality.checks.filter((check) => check.passed);
  const missing = quality.checks.filter((check) => !check.passed);

  return (
    <>
      <div className="flex flex-col gap-6 sm:flex-row sm:items-start sm:gap-10">
        <div className="shrink-0">
          <p className="font-mono text-[40px] leading-none font-medium text-fg tabular-nums">
            {quality.score}
            <span className="text-[20px] text-faint">/100</span>
          </p>
          <div className="mt-3 h-1 w-40 overflow-hidden rounded-full bg-line" aria-hidden="true">
            <div className={cn("h-full rounded-full", scoreTone(quality.score))} style={{ width: `${quality.score}%` }} />
          </div>
        </div>
        <div className="min-w-0">
          <p className="text-[16px] font-medium text-fg">{quality.label}</p>
          <p className="mt-1 text-[14px] leading-relaxed text-muted">{quality.interpretation}</p>
          <p className="mt-2 text-[12.5px] text-faint">
            Heuristic estimate based on detected README sections
            {quality.path && (
              <>
                {" "}
                in <span className="font-mono">{quality.path}</span>
              </>
            )}
            . Points count only when a section has real content or a recognisable command.
          </p>
          {quality.notes.map((note) => (
            <p key={note} className="mt-2 text-[13px] text-amber">
              <InlineText text={note} />
            </p>
          ))}
        </div>
      </div>

      <div className="grid gap-8 border-t border-line pt-8 lg:grid-cols-2">
        <section aria-labelledby="readme-strengths">
          <Eyebrow>
            <span id="readme-strengths">Strengths</span>
          </Eyebrow>
          {strengths.length === 0 ? (
            <p className="mt-3 text-[14px] text-faint">No onboarding sections were detected.</p>
          ) : (
            <ul className="mt-3 space-y-4">
              {strengths.map((check) => (
                <li key={check.key}>
                  <div className="flex items-baseline justify-between gap-3">
                    <p className="text-[14px] text-fg">
                      <span aria-hidden="true" className="mr-2 text-teal">
                        ✓
                      </span>
                      {check.label}
                    </p>
                    <span className="font-mono text-[12px] text-faint tabular-nums">
                      +{check.points}
                    </span>
                  </div>
                  {check.evidence.length > 0 && (
                    <ul className="mt-1 ml-5 space-y-0.5">
                      {check.evidence.map((item) => (
                        <li key={item} className="font-mono text-[12px] break-words text-faint">
                          {item.replace(/`/g, "")}
                        </li>
                      ))}
                    </ul>
                  )}
                </li>
              ))}
            </ul>
          )}
        </section>

        <section aria-labelledby="readme-missing">
          <Eyebrow>
            <span id="readme-missing">Missing or weak</span>
          </Eyebrow>
          {missing.length === 0 ? (
            <p className="mt-3 text-[14px] text-faint">Every rubric item was found.</p>
          ) : (
            <ul className="mt-3 space-y-2.5">
              {missing.map((check) => (
                <li key={check.key} className="flex items-baseline justify-between gap-3">
                  <p className="text-[14px] text-muted">
                    <span aria-hidden="true" className="mr-2 text-rose">
                      ○
                    </span>
                    {missingLabel(check)}
                    <span className="sr-only"> (not detected)</span>
                  </p>
                  <span className="font-mono text-[12px] text-faint tabular-nums">0/{check.max_points}</span>
                </li>
              ))}
            </ul>
          )}
        </section>
      </div>

      {missing.length > 0 && (
        <section aria-labelledby="readme-improvements" className="border-t border-line pt-8">
          <Eyebrow>
            <span id="readme-improvements">Suggested improvements</span>
          </Eyebrow>
          <ol className="mt-3 max-w-3xl list-decimal space-y-2 pl-5 text-[14px] leading-relaxed text-muted marker:font-mono marker:text-faint">
            {missing.map((check) => (
              <li key={check.key} className="pl-1">
                <InlineText text={check.suggestion} />
              </li>
            ))}
          </ol>
        </section>
      )}
    </>
  );
}

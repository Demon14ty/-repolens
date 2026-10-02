"use client";

import type { FirstThirtyPlan } from "@/lib/types";
import { progressKey, useStoredProgress } from "@/lib/use-progress";
import { categoryLabel, cn, plural } from "@/lib/utils";
import { EmptyState } from "./empty-state";
import { InlineText } from "./inline-text";
import { Eyebrow, SectionHeader } from "./section-header";
import { CitationList } from "./source-citation";

export function FirstThirtyMinutes({ analysisId, plan }: { analysisId: string; plan: FirstThirtyPlan | null }) {
  return (
    <div className="space-y-8">
      <SectionHeader
        id="section-first-30"
        title="First 30 Minutes"
        description="A short, focused reading plan: the few files that explain most of this repository."
        aside={plan && plan.steps.length > 0 ? <TotalTime minutes={plan.total_minutes} /> : undefined}
      />
      {plan && plan.steps.length > 0 ? (
        <Plan analysisId={analysisId} plan={plan} />
      ) : (
        <EmptyState title="No short plan for this repository">
          RepoLens could not find enough analysed files to build a reliable First 30 Minutes plan.
        </EmptyState>
      )}
    </div>
  );
}

function TotalTime({ minutes }: { minutes: number }) {
  return (
    <p className="text-right">
      <span className="font-mono text-[22px] font-medium text-fg tabular-nums">~{minutes}</span>
      <span className="ml-1 text-[13px] text-muted">min total</span>
    </p>
  );
}

function Plan({ analysisId, plan }: { analysisId: string; plan: FirstThirtyPlan }) {
  const [done, toggle] = useStoredProgress(progressKey(analysisId, "first30"));
  const completed = plan.steps.filter((step) => done.has(step.number)).length;

  return (
    <>
      <div>
        <p className="max-w-2xl text-[15px] leading-relaxed text-fg">
          Skim these {plural(plan.steps.length, "file")} in order to see what the project does, where it starts and
          where the real work happens. Details can wait.
        </p>
        {plan.limited_notice && <p className="mt-2 text-[14px] text-amber">{plan.limited_notice}</p>}
        <div className="mt-4 flex items-center gap-3">
          <div
            className="h-1 w-40 overflow-hidden rounded-full bg-line"
            role="progressbar"
            aria-label="Steps completed"
            aria-valuemin={0}
            aria-valuemax={plan.steps.length}
            aria-valuenow={completed}
          >
            <div
              className="h-full rounded-full bg-teal transition-[width]"
              style={{ width: `${(completed / plan.steps.length) * 100}%` }}
            />
          </div>
          <p className="text-[13px] text-muted tabular-nums">
            {completed} of {plan.steps.length} done
          </p>
        </div>
      </div>

      <ol className="divide-y divide-line border-y border-line">
        {plan.steps.map((step) => {
          const isDone = done.has(step.number);
          const checkboxId = `first30-${step.number}`;
          return (
            <li key={step.number} className="py-6">
              <div className="flex gap-4">
                <span
                  aria-hidden="true"
                  className="mt-0.5 w-6 shrink-0 font-mono text-[13px] text-faint tabular-nums"
                >
                  {String(step.number).padStart(2, "0")}
                </span>
                <div className="min-w-0 flex-1">
                  <div className="flex flex-col gap-1 sm:flex-row sm:items-baseline sm:justify-between sm:gap-4">
                    <h3 className={cn("font-mono text-[15px] break-all", isDone ? "text-muted" : "text-fg")}>
                      {step.path}
                    </h3>
                    <p className="shrink-0 text-[13px] text-faint">
                      {step.minutes} min · {categoryLabel(step.category)}
                    </p>
                  </div>
                  <dl className="mt-3 grid gap-3 text-[14px] leading-relaxed sm:grid-cols-[130px_1fr] sm:gap-x-4">
                    <dt className="text-faint">Why it matters</dt>
                    <dd className="text-muted">
                      <InlineText text={step.why} />
                    </dd>
                    <dt className="text-faint">What to look for</dt>
                    <dd className="text-muted">
                      <InlineText text={step.look_for} />
                    </dd>
                  </dl>
                  <CitationList citations={step.citations} label="Source" />
                  <div className="mt-4 flex items-center gap-2.5">
                    <input
                      id={checkboxId}
                      type="checkbox"
                      checked={isDone}
                      onChange={() => toggle(step.number)}
                      className="size-4 rounded border-line-strong accent-teal"
                    />
                    <label htmlFor={checkboxId} className="text-[13px] text-muted select-none">
                      {isDone ? "Read" : "Mark as read"}
                      <span className="sr-only">: {step.path}</span>
                    </label>
                  </div>
                </div>
              </div>
            </li>
          );
        })}
      </ol>

      {plan.outcomes.length > 0 && (
        <section aria-labelledby="outcomes-heading">
          <Eyebrow>
            <span id="outcomes-heading">After this, you should understand</span>
          </Eyebrow>
          <ul className="mt-3 grid gap-2 text-[14px] text-muted sm:grid-cols-2">
            {plan.outcomes.map((outcome) => (
              <li key={outcome} className="flex gap-2.5">
                <span aria-hidden="true" className="text-teal">
                  ✓
                </span>
                {outcome}
              </li>
            ))}
          </ul>
        </section>
      )}
    </>
  );
}

"use client";

import type { LearningStep } from "@/lib/types";
import { progressKey, useStoredProgress } from "@/lib/use-progress";
import { categoryLabel, cn } from "@/lib/utils";
import { EmptyState } from "./empty-state";
import { InlineText } from "./inline-text";
import { SectionHeader } from "./section-header";
import { CitationList } from "./source-citation";

const DIFFICULTY_STYLE: Record<string, string> = {
  Beginner: "text-teal",
  Intermediate: "text-amber",
  Advanced: "text-rose",
};

export function LearningPath({
  analysisId,
  steps,
  estimatedMinutes,
  explanations,
}: {
  analysisId: string;
  steps: LearningStep[];
  estimatedMinutes: number;
  explanations: Record<string, string>;
}) {
  return (
    <div className="space-y-8">
      <SectionHeader
        id="section-learning-path"
        title="Learning Path"
        description="The full reading order: README first, then the entry point, then the files it uses, closest first."
        aside={
          steps.length > 0 ? (
            <p className="text-right">
              <span className="font-mono text-[22px] font-medium text-fg tabular-nums">~{estimatedMinutes}</span>
              <span className="ml-1 text-[13px] text-muted">min total</span>
            </p>
          ) : undefined
        }
      />
      {steps.length > 0 ? (
        <Timeline analysisId={analysisId} steps={steps} explanations={explanations} />
      ) : (
        <EmptyState title="No learning path yet">
          RepoLens could not find enough evidence in this repository to build a reliable reading order.
        </EmptyState>
      )}
    </div>
  );
}

function Timeline({
  analysisId,
  steps,
  explanations,
}: {
  analysisId: string;
  steps: LearningStep[];
  explanations: Record<string, string>;
}) {
  const [done, toggle] = useStoredProgress(progressKey(analysisId, "path"));
  const completed = steps.filter((step) => done.has(step.number)).length;

  return (
    <>
      <p className="text-[13px] text-muted tabular-nums">
        {completed} of {steps.length} files read · reading times and difficulty are heuristic estimates
      </p>
      <ol className="relative">
        {steps.map((step, index) => {
          const isDone = done.has(step.number);
          const explanation = explanations[step.path];
          const checkboxId = `path-${step.number}`;
          return (
            <li key={step.number} className="relative flex gap-4 pb-9 last:pb-0 sm:gap-5">
              {index < steps.length - 1 && (
                <span aria-hidden="true" className="absolute top-8 bottom-1 left-[13px] w-px bg-line" />
              )}
              <span
                aria-hidden="true"
                className={cn(
                  "relative flex size-7 shrink-0 items-center justify-center rounded-full border font-mono text-[12px] tabular-nums",
                  isDone ? "border-teal/50 bg-teal-soft text-teal" : "border-line-strong bg-bg text-muted",
                )}
              >
                {isDone ? "✓" : step.number}
              </span>
              <div className="min-w-0 flex-1 pt-0.5">
                <h3 className="font-mono text-[15px] break-all text-fg">
                  <span className="sr-only">Step {step.number}: </span>
                  {step.path}
                </h3>
                <p className="mt-1 flex flex-wrap gap-x-2 text-[13px] text-faint">
                  <span className={DIFFICULTY_STYLE[step.difficulty_label] ?? "text-muted"}>
                    {step.difficulty_label}
                  </span>
                  <span aria-hidden="true">·</span>
                  <span>{step.minutes} min</span>
                  <span aria-hidden="true">·</span>
                  <span>{categoryLabel(step.category)}</span>
                  {step.prerequisites.length > 0 && (
                    <>
                      <span aria-hidden="true">·</span>
                      <span>after step {step.prerequisites.join(", ")}</span>
                    </>
                  )}
                </p>
                <p className="mt-3 max-w-2xl text-[14px] leading-relaxed text-muted">
                  <InlineText text={explanation || step.why} />
                </p>
                {explanation && (
                  <p className="mt-1 text-[12px] text-faint">
                    AI-worded. RepoLens reason: <InlineText text={step.why} />
                  </p>
                )}
                {step.relevant_code.length > 0 && (
                  <div className="mt-3">
                    <p className="text-[13px] text-faint">What to look for</p>
                    <ul className="mt-1 flex flex-wrap gap-x-4 gap-y-1">
                      {step.relevant_code.map((symbol) => (
                        <li key={symbol} className="font-mono text-[12.5px] text-fg/85">
                          {symbol}
                        </li>
                      ))}
                    </ul>
                  </div>
                )}
                <CitationList citations={step.citations} label="Source" />
                <div className="mt-3 flex items-center gap-2.5">
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
            </li>
          );
        })}
      </ol>
    </>
  );
}

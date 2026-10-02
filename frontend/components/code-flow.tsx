import type { FlowStep } from "@/lib/types";
import { cn } from "@/lib/utils";
import { InlineText } from "./inline-text";

/**
 * The main execution flow as a vertical sequence. Steps without a file are the
 * generic start/end of the flow and are drawn quieter than evidence-backed steps.
 */
export function CodeFlow({ steps }: { steps: FlowStep[] }) {
  return (
    <ol className="relative">
      {steps.map((step, index) => {
        const isEdge = !step.path;
        const last = index === steps.length - 1;
        return (
          <li key={`${step.label}-${index}`} className="relative flex gap-4 pb-5 last:pb-0">
            {!last && (
              <span aria-hidden="true" className="absolute top-5 bottom-0 left-[7px] w-px bg-line-strong" />
            )}
            <span
              aria-hidden="true"
              className={cn(
                "relative mt-1.5 size-[15px] shrink-0 rounded-full border-2",
                isEdge ? "border-line-strong bg-bg" : "border-accent bg-accent-soft",
              )}
            />
            <div className="min-w-0 flex-1">
              <p className={cn("text-[14px]", isEdge ? "text-muted" : "font-medium text-fg")}>{step.label}</p>
              {step.path && <p className="mt-0.5 font-mono text-[13px] break-all text-accent-strong">{step.path}</p>}
              {step.detail && (
                <p className="mt-1 text-[13px] leading-relaxed text-faint">
                  <InlineText text={step.detail} />
                </p>
              )}
            </div>
          </li>
        );
      })}
    </ol>
  );
}

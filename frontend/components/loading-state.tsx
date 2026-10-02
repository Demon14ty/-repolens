"use client";

import { useEffect, useState } from "react";
import { Check } from "lucide-react";
import { cn } from "@/lib/utils";

const STAGES = [
  "Validating repository URL",
  "Reading repository structure",
  "Detecting framework and dependencies",
  "Analysing Python files",
  "Building your learning path",
  "Preparing evidence-based answers",
];
const STAGE_INTERVAL_MS = 1700;

/**
 * The API returns one response, so real progress cannot be measured. The stages
 * advance on a gentle timer and the last one stays active until the result
 * arrives. No percentages are shown.
 */
export function LoadingState({ repository }: { repository: string }) {
  const [active, setActive] = useState(0);

  useEffect(() => {
    const timer = window.setInterval(() => {
      setActive((current) => Math.min(current + 1, STAGES.length - 1));
    }, STAGE_INTERVAL_MS);
    return () => window.clearInterval(timer);
  }, []);

  return (
    <div className="mx-auto max-w-xl py-16 sm:py-24" role="status" aria-live="polite">
      <p className="font-mono text-[12px] tracking-[0.12em] text-faint uppercase">Analysing</p>
      <p className="mt-2 font-mono text-[15px] break-all text-fg">{repository}</p>
      <ol className="mt-8 space-y-3.5">
        {STAGES.map((stage, index) => {
          const state = index < active ? "done" : index === active ? "active" : "pending";
          return (
            <li key={stage} className="flex items-center gap-3 text-[14px]">
              <span
                aria-hidden="true"
                className={cn(
                  "flex size-5 shrink-0 items-center justify-center rounded-full border",
                  state === "done" && "border-line-strong bg-raised text-muted",
                  state === "active" && "border-accent/60",
                  state === "pending" && "border-line",
                )}
              >
                {state === "done" && <Check className="size-3" strokeWidth={2.5} />}
                {state === "active" && <span className="rl-pulse size-1.5 rounded-full bg-accent" />}
              </span>
              <span
                className={cn(
                  state === "done" && "text-muted",
                  state === "active" && "text-fg",
                  state === "pending" && "text-faint",
                )}
              >
                {stage}
                {state === "active" && <span className="sr-only"> (in progress)</span>}
              </span>
            </li>
          );
        })}
      </ol>
      <p className="mt-8 text-[13px] text-faint">
        RepoLens reads the repository through GitHub without running any code. Larger repositories take longer.
      </p>
    </div>
  );
}

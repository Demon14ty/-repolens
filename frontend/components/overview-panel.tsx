"use client";

import Link from "next/link";
import type { AIExplanation, Analysis } from "@/lib/types";
import { CodeFlow } from "./code-flow";
import { ConfidenceBadge } from "./confidence-badge";
import { EmptyState } from "./empty-state";
import { ErrorState } from "./error-state";
import { InlineText } from "./inline-text";
import { Eyebrow, SectionHeader } from "./section-header";
import { CitationList } from "./source-citation";

export type ExplanationState =
  | { kind: "idle" }
  | { kind: "loading" }
  | { kind: "done"; result: AIExplanation }
  | { kind: "failed"; message: string };

export function OverviewPanel({
  analysis,
  explanation,
  onExplain,
}: {
  analysis: Analysis;
  explanation: ExplanationState;
  onExplain: () => void;
}) {
  const { framework, entry_point: entry, beginner_score: score } = analysis;

  return (
    <div className="space-y-10">
      <SectionHeader id="section-overview" title="Overview" description="What this repository is and where it starts." />

      {analysis.status === "unsupported" && (
        <ErrorState
          tone="notice"
          title="No Python application code to analyse"
          message={`RepoLens found the repository, but no Python application code it could analyse. GitHub reports the main language as ${analysis.repository.language}.`}
          suggestion="RepoLens currently supports Python repositories. The README review and repository questions below still work."
        />
      )}
      {analysis.status === "partial" && (
        <div className="rounded-[12px] border border-amber/30 bg-amber-soft px-5 py-4 text-[14px] leading-relaxed text-muted">
          <p className="font-medium text-fg">Partially analysed</p>
          <p className="mt-1">
            This repository is larger than RepoLens reads in one pass, or some files could not be downloaded.{" "}
            {analysis.files_summary.analysed_python_files} of {analysis.files_summary.python_files_in_tree} Python
            files were analysed, favouring entry points and shallow files. Results cover those files only.
          </p>
        </div>
      )}

      <section aria-labelledby="summary-heading">
        <h3 id="summary-heading" className="sr-only">
          Summary
        </h3>
        <p className="max-w-3xl text-[16px] leading-relaxed text-fg">
          <InlineText text={analysis.summary} />
        </p>
        {analysis.ai_explanations_available && analysis.learning_path.length > 0 && (
          <AiExplanation explanation={explanation} onExplain={onExplain} />
        )}
      </section>

      <section aria-label="Framework and entry point" className="grid overflow-hidden rounded-[12px] border border-line md:grid-cols-2">
        <div className="p-5 sm:p-6">
          <Eyebrow>Framework</Eyebrow>
          <div className="mt-3 flex flex-wrap items-center gap-2.5">
            <p className="text-[18px] font-semibold text-fg">{framework.name}</p>
            <ConfidenceBadge level={framework.confidence} />
          </div>
          {framework.evidence.length > 0 && (
            <div className="mt-4">
              <Eyebrow as="p">Evidence</Eyebrow>
              <ul className="mt-1.5 space-y-1.5 text-[14px] leading-relaxed text-muted">
                {framework.evidence.map((item) => (
                  <li key={item} className="flex gap-2">
                    <span aria-hidden="true" className="text-faint">
                      –
                    </span>
                    <span>
                      <InlineText text={item} />
                    </span>
                  </li>
                ))}
              </ul>
            </div>
          )}
          {framework.others.length > 0 && (
            <p className="mt-3 text-[13px] text-faint">Also found: {framework.others.join(", ")}</p>
          )}
        </div>

        <div className="border-t border-line p-5 sm:p-6 md:border-t-0 md:border-l">
          <Eyebrow>Likely entry point</Eyebrow>
          {entry ? (
            <>
              <p className="mt-3 font-mono text-[16px] break-all text-fg">{entry.path}</p>
              {entry.reasons.length > 0 && (
                <>
                  <p className="mt-3 text-[14px] text-muted">Detected because:</p>
                  <ul className="mt-1.5 space-y-1 text-[14px] leading-relaxed text-muted">
                    {entry.reasons.map((reason) => (
                      <li key={reason} className="flex gap-2">
                        <span aria-hidden="true" className="text-faint">
                          –
                        </span>
                        <span>
                          <InlineText text={reason} />
                        </span>
                      </li>
                    ))}
                  </ul>
                </>
              )}
              <CitationList citations={entry.citations} />
              {entry.others.length > 0 && (
                <p className="mt-3 text-[13px] text-faint">
                  Other candidates: <span className="font-mono">{entry.others.join(", ")}</span>
                </p>
              )}
            </>
          ) : (
            <p className="mt-3 text-[14px] leading-relaxed text-muted">
              RepoLens looked for <code className="font-mono text-fg">if __name__ == &quot;__main__&quot;</code> blocks,
              framework start-up calls and common entry-point file names, and found no likely entry point.
            </p>
          )}
        </div>
      </section>

      {score && (
        <section aria-labelledby="score-heading">
          <div className="flex flex-wrap items-baseline justify-between gap-2">
            <Eyebrow>
              <span id="score-heading">Beginner-friendliness</span>
            </Eyebrow>
            <p className="text-[12px] text-faint">Heuristic estimate built from the factors below.</p>
          </div>
          <ul className="mt-3 divide-y divide-line rounded-[12px] border border-line">
            {score.factors.map((factor) => (
              <li key={factor.label} className="flex flex-col gap-1 px-4 py-3 sm:flex-row sm:items-center sm:gap-4">
                <span className="text-[14px] text-fg sm:w-48 sm:shrink-0">{factor.label}</span>
                <span className="flex-1 text-[13px] text-muted">
                  <InlineText text={factor.reason} />
                </span>
                <span className="font-mono text-[13px] text-muted tabular-nums">
                  {factor.points}
                  <span className="text-faint">/{factor.max_points}</span>
                </span>
              </li>
            ))}
          </ul>
        </section>
      )}

      <section aria-labelledby="flow-heading">
        <Eyebrow>
          <span id="flow-heading">Main code flow</span>
        </Eyebrow>
        <p className="mt-1 text-[13px] text-faint">
          Built only from relationships found in the source: imports, route decorators and render calls.
        </p>
        <div className="mt-5">
          {analysis.code_flow.length > 0 ? (
            <CodeFlow steps={analysis.code_flow} />
          ) : (
            <EmptyState title="Not enough evidence for a flow">
              RepoLens could not find an entry point or route handlers to connect, so it does not guess one.
            </EmptyState>
          )}
        </div>
      </section>

      {analysis.warnings.length > 0 && (
        <section aria-labelledby="caveats-heading">
          <Eyebrow>
            <span id="caveats-heading">Caveats</span>
          </Eyebrow>
          <ul className="mt-3 space-y-2 text-[14px] leading-relaxed text-muted">
            {analysis.warnings.map((warning) => (
              <li key={warning} className="flex gap-2">
                <span aria-hidden="true" className="text-amber">
                  ·
                </span>
                <span>
                  <InlineText text={warning} />
                </span>
              </li>
            ))}
          </ul>
        </section>
      )}

      {analysis.status === "unsupported" && (
        <p className="text-[13px] text-faint">
          <Link href="/" className="underline underline-offset-4 hover:text-fg">
            Analyse a different repository
          </Link>
        </p>
      )}
    </div>
  );
}

function AiExplanation({ explanation, onExplain }: { explanation: ExplanationState; onExplain: () => void }) {
  if (explanation.kind === "done" && explanation.result.available) {
    const { result } = explanation;
    return (
      <div className="mt-5 max-w-3xl border-l-2 border-accent/50 pl-4">
        <Eyebrow as="p">Plain-language explanation</Eyebrow>
        {result.overview && (
          <p className="mt-2 text-[15px] leading-relaxed text-muted">
            <InlineText text={result.overview} />
          </p>
        )}
        <p className="mt-2 text-[12px] text-faint">{result.message}</p>
        {result.warnings.map((warning) => (
          <p key={warning} className="mt-1 text-[12px] text-amber">
            {warning}
          </p>
        ))}
      </div>
    );
  }
  const message =
    explanation.kind === "failed"
      ? explanation.message
      : explanation.kind === "done"
        ? explanation.result.message
        : null;
  return (
    <div className="mt-4 flex flex-wrap items-center gap-3">
      <button
        type="button"
        onClick={onExplain}
        disabled={explanation.kind === "loading"}
        className="inline-flex h-8 items-center rounded-lg border border-line px-3 text-[13px] text-muted hover:border-line-strong hover:text-fg disabled:opacity-60"
      >
        {explanation.kind === "loading" ? "Writing explanation…" : "Explain in plain language (optional AI)"}
      </button>
      {message && <p className="text-[13px] text-faint">{message}</p>}
    </div>
  );
}

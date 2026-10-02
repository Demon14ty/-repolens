import type { ContributionQuest as Quest } from "@/lib/types";
import { EmptyState } from "./empty-state";
import { InlineText } from "./inline-text";
import { Eyebrow, SectionHeader } from "./section-header";
import { CitationList } from "./source-citation";

export function ContributionQuest({ quest, aiText }: { quest: Quest | null; aiText: Record<string, string> }) {
  return (
    <div className="space-y-8">
      <SectionHeader
        id="section-quest"
        title="Contribution Quest"
        description="One small task grounded in evidence from this repository's code."
      />
      {quest ? (
        <Callout quest={quest} aiText={aiText} />
      ) : (
        <EmptyState title="No grounded task found">
          RepoLens could not find enough evidence in this repository to suggest a first task, so it does not invent
          one.
        </EmptyState>
      )}
    </div>
  );
}

function Callout({ quest, aiText }: { quest: Quest; aiText: Record<string, string> }) {
  const title = aiText.title || quest.title;
  const problem = aiText.problem || quest.problem;
  const why = aiText.why_useful || quest.why_useful;
  const hint = aiText.hint || quest.hint;

  return (
    <article className="relative rounded-[12px] border border-line bg-surface">
      <div aria-hidden="true" className="absolute top-6 bottom-6 left-0 w-0.5 rounded-full bg-accent" />
      <div className="px-6 py-7 sm:px-9 sm:py-9">
        <p className="font-mono text-[12px] tracking-[0.12em] text-accent uppercase">A good first contribution</p>
        <h3 className="mt-3 text-[22px] leading-snug font-semibold tracking-[-0.01em] text-balance text-fg">
          <InlineText text={title} />
        </h3>
        <p className="mt-3 flex flex-wrap gap-x-2 text-[13px] text-muted">
          <span>{quest.difficulty}</span>
          <span aria-hidden="true" className="text-faint">
            ·
          </span>
          <span>about {quest.minutes} minutes</span>
        </p>

        <dl className="mt-7 grid gap-x-8 gap-y-6 text-[14px] leading-relaxed sm:grid-cols-[150px_1fr]">
          <dt className="text-faint">Goal</dt>
          <dd className="text-fg">
            <InlineText text={problem} />
          </dd>

          <dt className="text-faint">Why it helps</dt>
          <dd className="text-muted">
            <InlineText text={why} />
          </dd>

          <dt className="text-faint">Likely files</dt>
          <dd>
            <ul className="space-y-0.5">
              {quest.likely_files.map((file) => (
                <li key={file} className="font-mono text-[13px] break-all text-fg">
                  {file}
                </li>
              ))}
            </ul>
          </dd>

          <dt className="text-faint">Concepts practised</dt>
          <dd className="text-muted">{quest.concepts.join(" · ")}</dd>

          <dt className="text-faint">Done when</dt>
          <dd>
            <ul className="space-y-1.5 text-muted">
              {quest.success_criteria.map((criterion) => (
                <li key={criterion} className="flex gap-2.5">
                  <span aria-hidden="true" className="text-faint">
                    □
                  </span>
                  <span>
                    <InlineText text={criterion} />
                  </span>
                </li>
              ))}
            </ul>
          </dd>
        </dl>

        {hint && (
          <details className="group mt-7 border-t border-line pt-5">
            <summary className="cursor-pointer text-[14px] text-muted select-none hover:text-fg">Show a hint</summary>
            <p className="mt-2 text-[14px] leading-relaxed text-muted">
              <InlineText text={hint} />
            </p>
          </details>
        )}

        <CitationList citations={quest.citations} />

        <div className="mt-7 border-t border-line pt-5">
          <Eyebrow as="p">Safety note</Eyebrow>
          <p className="mt-1.5 text-[13px] leading-relaxed text-muted">
            RepoLens never modifies the repository or opens pull requests. Work on your own fork or branch, keep the
            change small, and read the project&apos;s contribution guidelines before opening a pull request.
          </p>
        </div>
      </div>
    </article>
  );
}

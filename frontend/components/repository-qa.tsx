"use client";

import { useId, useState, type FormEvent } from "react";
import { ApiError, askQuestion } from "@/lib/api";
import type { QuestionAnswer } from "@/lib/types";
import { cn } from "@/lib/utils";
import { ConfidenceBadge } from "./confidence-badge";
import { InlineText } from "./inline-text";
import { Eyebrow, SectionHeader } from "./section-header";
import { SourceCitation } from "./source-citation";

const SUGGESTED_QUESTIONS = [
  "Where does the app start?",
  "Which framework does it use?",
  "Where are dependencies defined?",
  "Where are the tests?",
  "Does it use a database?",
  "How do I run it?",
];

const UNSUPPORTED_MESSAGE =
  "RepoLens currently supports questions about entry points, frameworks, dependencies, tests, databases, routes, UI files, setup commands, reading order, and code flow.";

export type QAEntry =
  | { id: number; question: string; status: "pending" }
  | { id: number; question: string; status: "answered"; answer: QuestionAnswer }
  | { id: number; question: string; status: "failed"; message: string };

export function RepositoryQA({
  analysisId,
  entries,
  onEntriesChange,
}: {
  analysisId: string;
  entries: QAEntry[];
  onEntriesChange: (update: (entries: QAEntry[]) => QAEntry[]) => void;
}) {
  const [draft, setDraft] = useState("");
  const inputId = useId();
  const pending = entries.some((entry) => entry.status === "pending");

  async function ask(question: string) {
    const text = question.trim();
    if (!text || pending) return;
    const id = entries.reduce((highest, entry) => Math.max(highest, entry.id), 0) + 1;
    onEntriesChange((current) => [{ id, question: text, status: "pending" }, ...current]);
    try {
      const answer = await askQuestion(analysisId, text);
      onEntriesChange((current) =>
        current.map((entry) => (entry.id === id ? { id, question: text, status: "answered", answer } : entry)),
      );
    } catch (error) {
      const message = error instanceof ApiError ? error.message : "RepoLens could not answer right now. Try again.";
      onEntriesChange((current) =>
        current.map((entry) => (entry.id === id ? { id, question: text, status: "failed", message } : entry)),
      );
    }
  }

  function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    void ask(draft);
    setDraft("");
  }

  return (
    <div className="space-y-8">
      <SectionHeader
        id="section-ask"
        title="Ask about this repository"
        description="Answers are based only on the files RepoLens analysed. Every source is checked against those files."
      />

      <div>
        <Eyebrow as="p">Suggested questions</Eyebrow>
        <ul className="mt-3 grid gap-2 sm:grid-cols-2 lg:grid-cols-3">
          {SUGGESTED_QUESTIONS.map((question) => (
            <li key={question}>
              <button
                type="button"
                onClick={() => void ask(question)}
                disabled={pending}
                className="w-full rounded-[10px] border border-line px-3.5 py-2.5 text-left text-[14px] text-muted transition-colors hover:border-line-strong hover:bg-raised hover:text-fg disabled:cursor-not-allowed disabled:opacity-60"
              >
                {question}
              </button>
            </li>
          ))}
        </ul>
      </div>

      <form onSubmit={submit} className="flex flex-col gap-2 sm:flex-row">
        <label htmlFor={inputId} className="sr-only">
          Your question
        </label>
        <input
          id={inputId}
          type="text"
          value={draft}
          maxLength={500}
          onChange={(event) => setDraft(event.target.value)}
          placeholder="e.g. Where are the API routes defined?"
          className="h-11 min-w-0 flex-1 rounded-[10px] border border-line-strong bg-surface px-3.5 text-[14px] text-fg placeholder:text-faint focus:border-accent focus:ring-2 focus:ring-accent/25 focus:outline-none focus-visible:outline-none"
        />
        <button
          type="submit"
          disabled={pending || !draft.trim()}
          className="inline-flex h-11 shrink-0 items-center justify-center rounded-[10px] bg-fg px-5 text-[14px] font-medium text-bg hover:bg-white disabled:cursor-not-allowed disabled:opacity-50"
        >
          Ask
        </button>
      </form>

      <div aria-live="polite" className="space-y-5">
        {entries.map((entry, index) => (
          <AnswerBlock key={entry.id} entry={entry} latest={index === 0} />
        ))}
      </div>
    </div>
  );
}

function AnswerBlock({ entry, latest }: { entry: QAEntry; latest: boolean }) {
  return (
    <article className={cn("rounded-[12px] border bg-surface", latest ? "border-line-strong" : "border-line")}>
      <header className="border-b border-line px-5 py-3">
        <p className="text-[14px] font-medium text-fg">{entry.question}</p>
      </header>
      <div className="px-5 py-4">
        {entry.status === "pending" && <p className="rl-pulse text-[14px] text-muted">Looking through the analysis…</p>}
        {entry.status === "failed" && <p className="text-[14px] text-rose">{entry.message}</p>}
        {entry.status === "answered" && <Answer answer={entry.answer} />}
      </div>
    </article>
  );
}

function Answer({ answer }: { answer: QuestionAnswer }) {
  if (answer.unsupported) {
    return (
      <div className="space-y-3">
        <ConfidenceBadge level="No reliable answer" />
        <p className="text-[14px] leading-relaxed text-muted">{UNSUPPORTED_MESSAGE}</p>
      </div>
    );
  }
  return (
    <div className="space-y-4">
      <p className="text-[14px] leading-relaxed text-fg">
        <InlineText text={answer.answer} />
      </p>
      <ConfidenceBadge level={answer.confidence} />
      {answer.citations.length > 0 && (
        <div>
          <Eyebrow as="p">Sources</Eyebrow>
          <ul className="mt-1.5 space-y-0.5">
            {answer.citations.map((citation) => (
              <li key={`${citation.path}:${citation.start_line}-${citation.end_line}`}>
                <SourceCitation citation={citation} />
              </li>
            ))}
          </ul>
        </div>
      )}
      {answer.limitations && (
        <p className="border-t border-line pt-3 text-[13px] leading-relaxed text-faint">
          <InlineText text={answer.limitations} />
        </p>
      )}
    </div>
  );
}

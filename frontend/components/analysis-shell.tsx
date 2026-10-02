"use client";

import Link from "next/link";
import { useSearchParams } from "next/navigation";
import { useCallback, useEffect, useRef, useState } from "react";
import { ArrowLeft, ExternalLink, RefreshCw } from "lucide-react";
import { ApiError, analyzeRepository, requestExplanation } from "@/lib/api";
import type { Analysis } from "@/lib/types";
import { canonicalRepositoryUrl, checkRepositoryUrl, cn, formatCount, readSession, writeSession } from "@/lib/utils";
import { ConfidenceBadge } from "./confidence-badge";
import { ConfusionMap } from "./confusion-map";
import { ContributionQuest } from "./contribution-quest";
import { ErrorState, errorCopy } from "./error-state";
import { FirstThirtyMinutes } from "./first-thirty-minutes";
import { FrameworkBadge } from "./framework-badge";
import { LearningPath } from "./learning-path";
import { LoadingState } from "./loading-state";
import { Wordmark } from "./navbar";
import { OverviewPanel, type ExplanationState } from "./overview-panel";
import { ReadmeQuality } from "./readme-quality";
import { RepositoryQA, type QAEntry } from "./repository-qa";
import { TechnicalDetails } from "./technical-details";

const SECTIONS = [
  { id: "overview", label: "Overview" },
  { id: "first-30", label: "First 30 Minutes" },
  { id: "learning-path", label: "Learning Path" },
  { id: "confusion-map", label: "Confusion Map" },
  { id: "readme", label: "README Review" },
  { id: "quest", label: "Contribution Quest" },
  { id: "ask", label: "Ask RepoLens" },
  { id: "technical", label: "Technical Details" },
] as const;
type SectionId = (typeof SECTIONS)[number]["id"];

type LoadState =
  | { kind: "loading" }
  | { kind: "ready"; analysis: Analysis }
  | { kind: "error"; code: string; title: string; message: string };

const ANALYSIS_CACHE_PREFIX = "repolens:analysis:";

function isAnalysis(value: unknown): value is Analysis {
  if (typeof value !== "object" || value === null) return false;
  const candidate = value as Partial<Analysis>;
  return (
    typeof candidate.analysis_id === "string" &&
    typeof candidate.status === "string" &&
    typeof candidate.repository === "object" &&
    Array.isArray(candidate.learning_path)
  );
}

function sectionFromHash(): SectionId {
  if (typeof window === "undefined") return "overview";
  const hash = window.location.hash.replace("#", "");
  return SECTIONS.find((section) => section.id === hash)?.id ?? "overview";
}

/** Reads ?repo=... and renders the loader. Changing the key remounts it, which resets all state. */
export function AnalysisShell() {
  const repoParam = useSearchParams().get("repo") ?? "";
  const [attempt, setAttempt] = useState({ count: 0, refresh: false });

  return (
    <AnalysisLoader
      key={`${repoParam}::${attempt.count}`}
      repoParam={repoParam}
      refresh={attempt.refresh}
      onReanalyze={() => setAttempt((current) => ({ count: current.count + 1, refresh: true }))}
      onRetry={() => setAttempt((current) => ({ count: current.count + 1, refresh: false }))}
    />
  );
}

function initialState(repoParam: string, refresh: boolean): { state: LoadState; repoUrl: string | null } {
  const check = checkRepositoryUrl(repoParam);
  if (!check.ok) {
    const copy = errorCopy("INVALID_REPOSITORY_URL", "", check.message);
    return {
      repoUrl: null,
      state: { kind: "error", code: "INVALID_REPOSITORY_URL", title: copy.title, message: check.message },
    };
  }
  const repoUrl = canonicalRepositoryUrl(check.owner, check.repo);
  if (!refresh) {
    const cached = readSession(ANALYSIS_CACHE_PREFIX + repoUrl.toLowerCase(), isAnalysis);
    if (cached) return { repoUrl, state: { kind: "ready", analysis: cached } };
  }
  return { repoUrl, state: { kind: "loading" } };
}

function AnalysisLoader({
  repoParam,
  refresh,
  onReanalyze,
  onRetry,
}: {
  repoParam: string;
  refresh: boolean;
  onReanalyze: () => void;
  onRetry: () => void;
}) {
  const [{ repoUrl, state: initial }] = useState(() => initialState(repoParam, refresh));
  const [state, setState] = useState<LoadState>(initial);
  const needsFetch = initial.kind === "loading";

  useEffect(() => {
    if (!needsFetch || !repoUrl) return;
    const controller = new AbortController();
    analyzeRepository(repoUrl, { refresh, signal: controller.signal })
      .then((analysis) => {
        writeSession(ANALYSIS_CACHE_PREFIX + repoUrl.toLowerCase(), analysis);
        setState({ kind: "ready", analysis });
      })
      .catch((error: unknown) => {
        if (controller.signal.aborted) return;
        const apiError =
          error instanceof ApiError
            ? error
            : new ApiError(0, { code: "UNKNOWN", title: "", message: "Something unexpected went wrong.", details: null });
        setState({ kind: "error", code: apiError.code, title: apiError.title, message: apiError.message });
      });
    return () => controller.abort();
  }, [needsFetch, repoUrl, refresh]);

  const displayName = state.kind === "ready" ? state.analysis.repository.full_name : repoUrl?.replace("https://github.com/", "");

  return (
    <div className="flex min-h-full flex-1 flex-col">
      <TopBar
        name={displayName ?? null}
        framework={state.kind === "ready" ? state.analysis.framework.name : null}
        language={state.kind === "ready" ? state.analysis.repository.language : null}
        onReanalyze={repoUrl && state.kind !== "loading" ? onReanalyze : undefined}
      />
      <main className="flex-1">
        {state.kind === "loading" && <LoadingState repository={repoUrl ?? repoParam} />}
        {state.kind === "error" && (
          <div className="mx-auto max-w-2xl px-4 py-16 sm:px-6">
            <ErrorView state={state} onRetry={repoUrl ? onRetry : undefined} />
          </div>
        )}
        {state.kind === "ready" && <ReadyView analysis={state.analysis} />}
      </main>
    </div>
  );
}

function ErrorView({
  state,
  onRetry,
}: {
  state: Extract<LoadState, { kind: "error" }>;
  onRetry?: () => void;
}) {
  const copy = errorCopy(state.code, state.title, state.message);
  return (
    <ErrorState
      title={copy.title}
      message={copy.message}
      suggestion={copy.suggestion}
      onRetry={copy.retry ? onRetry : undefined}
    />
  );
}

function TopBar({
  name,
  framework,
  language,
  onReanalyze,
}: {
  name: string | null;
  framework: string | null;
  language: string | null;
  onReanalyze?: () => void;
}) {
  const [owner, repo] = name ? name.split("/") : [null, null];
  return (
    <header className="sticky top-0 z-20 border-b border-line/70 bg-bg/90 backdrop-blur supports-[backdrop-filter]:bg-bg/75">
      <div className="mx-auto flex h-14 max-w-6xl items-center gap-3 px-4 sm:px-6">
        <Link
          href="/"
          className="inline-flex h-8 shrink-0 items-center gap-1.5 rounded-lg px-2 text-[13px] text-muted hover:bg-raised hover:text-fg"
        >
          <ArrowLeft aria-hidden="true" className="size-4" />
          <span className="hidden sm:inline">Home</span>
          <span className="sr-only sm:hidden">Back to home</span>
        </Link>
        <span aria-hidden="true" className="h-4 w-px shrink-0 bg-line-strong" />
        {owner && repo ? (
          <p className="min-w-0 truncate font-mono text-[13px]">
            <span className="text-faint">{owner} / </span>
            <span className="text-fg">{repo}</span>
          </p>
        ) : (
          <div className="min-w-0">
            <Wordmark />
          </div>
        )}
        {(framework || language) && (
          <FrameworkBadge
            name={framework && !framework.startsWith("Not determined") ? framework : (language ?? "")}
            className="hidden shrink-0 md:inline-flex"
          />
        )}
        <div className="ml-auto shrink-0">
          {onReanalyze && (
            <button
              type="button"
              onClick={onReanalyze}
              className="inline-flex h-8 items-center gap-2 rounded-lg border border-line px-3 text-[13px] text-muted hover:border-line-strong hover:text-fg"
            >
              <RefreshCw aria-hidden="true" className="size-3.5" />
              <span className="hidden sm:inline">Re-analyze</span>
              <span className="sr-only sm:hidden">Re-analyze repository</span>
            </button>
          )}
        </div>
      </div>
    </header>
  );
}

function SummaryHeader({ analysis }: { analysis: Analysis }) {
  const { repository: repo, framework, beginner_score: score } = analysis;
  const facts: { label: string; value: string }[] = [
    { label: "Stars", value: formatCount(repo.stars) },
    { label: "License", value: repo.license || "None detected" },
    { label: "Default branch", value: repo.default_branch },
    { label: "Language", value: repo.language },
  ];
  return (
    <section aria-labelledby="repo-title" className="border-b border-line/70">
      <div className="mx-auto max-w-6xl px-4 py-8 sm:px-6 sm:py-10">
        <h1 id="repo-title" className="text-[26px] leading-tight font-semibold tracking-[-0.015em] break-words sm:text-[30px]">
          <span className="text-faint">{repo.owner} / </span>
          <span className="text-fg">{repo.name}</span>
        </h1>
        {repo.description && <p className="mt-2 max-w-3xl text-[15px] leading-relaxed text-muted">{repo.description}</p>}

        <dl className="mt-6 grid gap-x-10 gap-y-5 sm:grid-cols-2 lg:flex lg:flex-wrap">
          <div>
            <dt className="text-[12px] text-faint">Framework</dt>
            <dd className="mt-1 flex flex-wrap items-center gap-2">
              <span className="text-[15px] text-fg">{framework.name}</span>
              <ConfidenceBadge level={framework.confidence} />
            </dd>
          </div>
          <div>
            <dt className="text-[12px] text-faint">Beginner-friendliness</dt>
            <dd className="mt-1 text-[15px] text-fg">
              {score ? (
                <>
                  <span className="font-mono tabular-nums">{score.score}</span>
                  <span className="text-faint">/100</span>
                  <span className="ml-2 text-muted">{score.label}</span>
                </>
              ) : (
                <span className="text-muted">Not available</span>
              )}
            </dd>
          </div>
          <div className="sm:col-span-2 lg:col-span-1">
            <dt className="sr-only">Repository metadata</dt>
            <dd className="flex flex-wrap items-center gap-x-4 gap-y-1 text-[13px] text-muted lg:mt-[22px]">
              {facts.map((fact) => (
                <span key={fact.label}>
                  <span className="text-faint">{fact.label} </span>
                  <span className={fact.label === "Default branch" ? "font-mono" : undefined}>{fact.value}</span>
                </span>
              ))}
              <a
                href={repo.html_url}
                target="_blank"
                rel="noreferrer"
                className="inline-flex items-center gap-1 rounded text-muted underline decoration-line-strong underline-offset-4 hover:text-fg"
              >
                View on GitHub
                <ExternalLink aria-hidden="true" className="size-3" />
              </a>
            </dd>
          </div>
        </dl>
      </div>
    </section>
  );
}

function SectionNav({
  active,
  onSelect,
  variant,
}: {
  active: SectionId;
  onSelect: (id: SectionId) => void;
  variant: "sidebar" | "bar";
}) {
  return (
    <nav
      aria-label="Analysis sections"
      className={cn(
        variant === "sidebar" && "sticky top-[76px] hidden lg:block",
        variant === "bar" &&
          "scroll-thin -mx-4 overflow-x-auto border-b border-line px-4 sm:-mx-6 sm:px-6 lg:hidden",
      )}
    >
      <ul className={cn(variant === "sidebar" ? "space-y-0.5" : "flex min-w-max gap-1")}>
        {SECTIONS.map((section) => {
          const isActive = section.id === active;
          return (
            <li key={section.id}>
              <button
                type="button"
                onClick={() => onSelect(section.id)}
                aria-current={isActive ? "true" : undefined}
                className={cn(
                  "text-[14px] transition-colors",
                  variant === "sidebar" &&
                    "relative w-full rounded-lg px-3 py-1.5 text-left hover:bg-raised hover:text-fg",
                  variant === "bar" && "border-b-2 px-2.5 py-3 whitespace-nowrap",
                  isActive
                    ? variant === "sidebar"
                      ? "bg-raised font-medium text-fg"
                      : "border-accent font-medium text-fg"
                    : variant === "sidebar"
                      ? "text-muted"
                      : "border-transparent text-muted hover:text-fg",
                )}
              >
                {variant === "sidebar" && isActive && (
                  <span aria-hidden="true" className="absolute top-2 bottom-2 left-0 w-0.5 rounded-full bg-accent" />
                )}
                {section.label}
              </button>
            </li>
          );
        })}
      </ul>
    </nav>
  );
}

function ReadyView({ analysis }: { analysis: Analysis }) {
  const [active, setActive] = useState<SectionId>(sectionFromHash);
  const [qaEntries, setQaEntries] = useState<QAEntry[]>([]);
  const [explanation, setExplanation] = useState<ExplanationState>({ kind: "idle" });
  const focusOnChange = useRef(false);

  const select = useCallback((id: SectionId) => {
    focusOnChange.current = true;
    setActive(id);
    window.history.replaceState(null, "", `${window.location.pathname}${window.location.search}#${id}`);
  }, []);

  useEffect(() => {
    if (!focusOnChange.current) return;
    focusOnChange.current = false;
    document.getElementById(`section-${active}`)?.focus();
  }, [active]);

  const explain = useCallback(() => {
    setExplanation({ kind: "loading" });
    requestExplanation(analysis.analysis_id)
      .then((result) => setExplanation({ kind: "done", result }))
      .catch((error: unknown) =>
        setExplanation({
          kind: "failed",
          message: error instanceof ApiError ? error.message : "The AI explanation could not be generated.",
        }),
      );
  }, [analysis.analysis_id]);

  const ai = explanation.kind === "done" && explanation.result.available ? explanation.result : null;

  return (
    <>
      <SummaryHeader analysis={analysis} />
      <div className="mx-auto max-w-6xl px-4 sm:px-6">
        <div className="lg:grid lg:grid-cols-[200px_minmax(0,1fr)] lg:gap-12">
          <div className="lg:py-10">
            <SectionNav active={active} onSelect={select} variant="sidebar" />
            <SectionNav active={active} onSelect={select} variant="bar" />
          </div>
          <div className="min-w-0 py-8 pb-24 lg:py-10">
            {active === "overview" && (
              <OverviewPanel analysis={analysis} explanation={explanation} onExplain={explain} />
            )}
            {active === "first-30" && (
              <FirstThirtyMinutes analysisId={analysis.analysis_id} plan={analysis.first_30_minutes} />
            )}
            {active === "learning-path" && (
              <LearningPath
                analysisId={analysis.analysis_id}
                steps={analysis.learning_path}
                estimatedMinutes={analysis.estimated_minutes}
                explanations={ai?.step_explanations ?? {}}
              />
            )}
            {active === "confusion-map" && <ConfusionMap map={analysis.confusion_map} skip={analysis.skip_for_now} />}
            {active === "readme" && <ReadmeQuality quality={analysis.readme_quality} />}
            {active === "quest" && (
              <ContributionQuest quest={analysis.contribution_quest} aiText={ai?.quest_text ?? {}} />
            )}
            {active === "ask" && (
              <RepositoryQA analysisId={analysis.analysis_id} entries={qaEntries} onEntriesChange={setQaEntries} />
            )}
            {active === "technical" && <TechnicalDetails analysis={analysis} />}
          </div>
        </div>
      </div>
    </>
  );
}

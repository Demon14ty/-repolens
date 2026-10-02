import Link from "next/link";
import { PROJECT_GITHUB_URL } from "@/lib/utils";

export function LensMark({ className = "size-5" }: { className?: string }) {
  return (
    <svg viewBox="0 0 24 24" fill="none" aria-hidden="true" className={className}>
      <circle cx="10.5" cy="10.5" r="6" stroke="currentColor" strokeWidth="2" className="text-accent" />
      <path d="M15 15l5 5" stroke="currentColor" strokeWidth="2" strokeLinecap="round" />
      <path d="M8 10.5h5" stroke="currentColor" strokeWidth="1.75" strokeLinecap="round" />
    </svg>
  );
}

export function GitHubMark({ className = "size-4" }: { className?: string }) {
  return (
    <svg viewBox="0 0 16 16" fill="currentColor" aria-hidden="true" className={className}>
      <path d="M8 0C3.58 0 0 3.58 0 8c0 3.54 2.29 6.53 5.47 7.59.4.07.55-.17.55-.38 0-.19-.01-.82-.01-1.49-2.01.37-2.53-.49-2.69-.94-.09-.23-.48-.94-.82-1.13-.28-.15-.68-.52-.01-.53.63-.01 1.08.58 1.23.82.72 1.21 1.87.87 2.33.66.07-.52.28-.87.51-1.07-1.78-.2-3.64-.89-3.64-3.95 0-.87.31-1.59.82-2.15-.08-.2-.36-1.02.08-2.12 0 0 .67-.21 2.2.82.64-.18 1.32-.27 2-.27.68 0 1.36.09 2 .27 1.53-1.04 2.2-.82 2.2-.82.44 1.1.16 1.92.08 2.12.51.56.82 1.27.82 2.15 0 3.07-1.87 3.75-3.65 3.95.29.25.54.73.54 1.48 0 1.07-.01 1.93-.01 2.2 0 .21.15.46.55.38A8.013 8.013 0 0016 8c0-4.42-3.58-8-8-8z" />
    </svg>
  );
}

export function Wordmark() {
  return (
    <Link href="/" className="group flex items-center gap-2.5 rounded-md">
      <LensMark />
      <span className="text-[15px] font-semibold tracking-tight text-fg">RepoLens</span>
      <span aria-hidden="true" className="hidden h-4 w-px bg-line-strong sm:block" />
      <span className="hidden text-[13px] text-faint sm:block">Repository onboarding</span>
    </Link>
  );
}

export function Navbar() {
  return (
    <header className="border-b border-line/70">
      <nav aria-label="Main" className="mx-auto flex h-14 max-w-6xl items-center justify-between gap-4 px-4 sm:px-6">
        <Wordmark />
        <div className="flex items-center gap-1 sm:gap-2">
          <a
            href={PROJECT_GITHUB_URL}
            target="_blank"
            rel="noreferrer"
            className="inline-flex h-8 items-center gap-2 rounded-lg px-2.5 text-[13px] text-muted transition-colors hover:bg-raised hover:text-fg"
          >
            <GitHubMark />
            <span className="hidden sm:inline">GitHub</span>
            <span className="sr-only sm:hidden">RepoLens on GitHub</span>
          </a>
          <Link
            href="/#analyze"
            className="inline-flex h-8 items-center rounded-lg border border-line px-3 text-[13px] font-medium text-fg transition-colors hover:border-line-strong hover:bg-raised"
          >
            Try RepoLens
          </Link>
        </div>
      </nav>
    </header>
  );
}

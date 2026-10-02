import { PROJECT_GITHUB_URL } from "@/lib/utils";
import { GitHubMark } from "./navbar";

export function Footer() {
  return (
    <footer className="mt-auto border-t border-line/70">
      <div className="mx-auto flex max-w-6xl flex-col gap-3 px-4 py-8 text-[13px] text-faint sm:flex-row sm:items-center sm:justify-between sm:px-6">
        <p>
          <span className="font-medium text-muted">RepoLens</span>
          <span className="mx-2" aria-hidden="true">
            ·
          </span>
          Built for learners and new contributors
        </p>
        <a
          href={PROJECT_GITHUB_URL}
          target="_blank"
          rel="noreferrer"
          className="inline-flex items-center gap-2 self-start rounded-md hover:text-fg sm:self-auto"
        >
          <GitHubMark className="size-3.5" />
          Source on GitHub
        </a>
      </div>
    </footer>
  );
}

import Link from "next/link";
import type { ReactNode } from "react";
import { CircleAlert } from "lucide-react";
import { cn } from "@/lib/utils";

interface ErrorCopy {
  title: string;
  message: string;
  suggestion: string;
  retry: boolean;
}

const COPY: Record<string, Omit<ErrorCopy, "message"> & { message?: string }> = {
  INVALID_REPOSITORY_URL: {
    title: "That is not a repository URL",
    suggestion: "Paste a link in the form https://github.com/owner/repository.",
    retry: false,
  },
  NOT_GITHUB_URL: {
    title: "Only GitHub repositories are supported",
    suggestion: "Paste a link in the form https://github.com/owner/repository.",
    retry: false,
  },
  REPOSITORY_NOT_FOUND: {
    title: "Repository unavailable",
    suggestion: "Check the owner and repository name for typos. Private repositories cannot be analysed.",
    retry: false,
  },
  REPOSITORY_INACCESSIBLE: {
    title: "This repository is private or restricted",
    suggestion: "RepoLens can only read public repositories. Try a public one instead.",
    retry: false,
  },
  GITHUB_RATE_LIMITED: {
    title: "GitHub is rate-limiting requests",
    suggestion:
      "Wait a few minutes and try again. If you run RepoLens yourself, setting GITHUB_TOKEN on the server raises the limit.",
    retry: true,
  },
  EMPTY_REPOSITORY: {
    title: "This repository is empty",
    suggestion: "Once code is pushed to the default branch, RepoLens can analyse it.",
    retry: false,
  },
  GITHUB_UNAVAILABLE: {
    title: "Could not reach GitHub",
    suggestion: "This is usually temporary. Try again in a moment.",
    retry: true,
  },
  NETWORK_ERROR: {
    title: "Could not reach RepoLens",
    suggestion: "Check your connection. If you are running RepoLens locally, make sure the API is running on port 8000.",
    retry: true,
  },
  SERVER_UNAVAILABLE: {
    title: "The analysis did not finish",
    suggestion: "Try again, or try a smaller repository.",
    retry: true,
  },
};

const FALLBACK: Omit<ErrorCopy, "message"> = {
  title: "Something went wrong",
  suggestion: "Try again. If it keeps happening, try a different repository.",
  retry: true,
};

export function errorCopy(code: string, apiTitle: string, apiMessage: string): ErrorCopy {
  const copy = COPY[code] ?? { ...FALLBACK, title: apiTitle || FALLBACK.title };
  return { ...copy, message: copy.message ?? apiMessage };
}

export function ErrorState({
  title,
  message,
  suggestion,
  onRetry,
  tone = "error",
  children,
}: {
  title: string;
  message: string;
  suggestion?: string;
  onRetry?: () => void;
  tone?: "error" | "notice";
  children?: ReactNode;
}) {
  return (
    <div
      role={tone === "error" ? "alert" : undefined}
      className={cn(
        "rounded-[12px] border bg-surface px-5 py-6 sm:px-7 sm:py-7",
        tone === "error" ? "border-rose/30" : "border-amber/30",
      )}
    >
      <div className="flex items-start gap-3">
        <CircleAlert
          aria-hidden="true"
          className={cn("mt-0.5 size-[18px] shrink-0", tone === "error" ? "text-rose" : "text-amber")}
          strokeWidth={1.75}
        />
        <div className="min-w-0">
          <h2 className="text-[17px] font-semibold text-fg">{title}</h2>
          <p className="mt-2 text-[14px] leading-relaxed text-muted">{message}</p>
          {suggestion && (
            <p className="mt-2 text-[14px] leading-relaxed text-muted">
              <span className="font-medium text-fg">What to try: </span>
              {suggestion}
            </p>
          )}
          {children}
          <div className="mt-5 flex flex-wrap gap-2">
            {onRetry && (
              <button
                type="button"
                onClick={onRetry}
                className="inline-flex h-9 items-center rounded-lg bg-fg px-4 text-[13px] font-medium text-bg hover:bg-white"
              >
                Try again
              </button>
            )}
            <Link
              href="/"
              className="inline-flex h-9 items-center rounded-lg border border-line-strong px-4 text-[13px] font-medium text-fg hover:bg-raised"
            >
              Back to home
            </Link>
          </div>
        </div>
      </div>
    </div>
  );
}

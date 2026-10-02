import { clsx, type ClassValue } from "clsx";

export function cn(...inputs: ClassValue[]): string {
  return clsx(inputs);
}

export const PROJECT_GITHUB_URL = "https://github.com/Demon14ty/-repolens";
export const EXAMPLE_REPOSITORY = "https://github.com/miguelgrinberg/microblog";

// Mirrors utils/github_parser.py so obvious typos are caught before a request is sent.
// The API remains the source of truth and validates again.
const GITHUB_REPO_PATTERN =
  /^(?:https?:\/\/)?(?:www\.)?github\.com\/([A-Za-z0-9](?:[A-Za-z0-9-]{0,38}))\/([A-Za-z0-9._-]+?)(?:\.git)?(?:\/.*)?$/i;
const SSH_PATTERN = /^git@github\.com:([A-Za-z0-9](?:[A-Za-z0-9-]{0,38}))\/([A-Za-z0-9._-]+?)(?:\.git)?$/i;
const RESERVED_OWNERS = new Set(["orgs", "settings", "marketplace", "explore", "topics", "features", "login", "about"]);

export type UrlCheck = { ok: true; owner: string; repo: string } | { ok: false; message: string };

export function checkRepositoryUrl(input: string): UrlCheck {
  const text = input.trim().split(/[?#]/, 1)[0].replace(/\/+$/, "");
  if (!text) return { ok: false, message: "Enter a GitHub repository URL." };
  const match = GITHUB_REPO_PATTERN.exec(text) ?? SSH_PATTERN.exec(text);
  if (!match) {
    const looksLikeOtherHost = /^(https?:\/\/)?[\w.-]+\.[a-z]{2,}\//i.test(text) && !/github\.com/i.test(text);
    return {
      ok: false,
      message: looksLikeOtherHost
        ? "RepoLens reads repositories hosted on github.com."
        : "Use the format https://github.com/owner/repository.",
    };
  }
  const [, owner, repo] = match;
  if (RESERVED_OWNERS.has(owner.toLowerCase()) || repo === "." || repo === "..") {
    return { ok: false, message: "That link points to a GitHub page, not a repository." };
  }
  return { ok: true, owner, repo };
}

/** Canonical form used for routing and storage keys. */
export function canonicalRepositoryUrl(owner: string, repo: string): string {
  return `https://github.com/${owner}/${repo}`;
}

export function analyzeHref(repoUrl: string): string {
  return `/analyze?repo=${encodeURIComponent(repoUrl)}`;
}

export function formatLineRange(start: number, end: number): string {
  return start === end ? `line ${start}` : `lines ${start}–${end}`;
}

export function formatCount(value: number): string {
  return new Intl.NumberFormat("en", { notation: value >= 10_000 ? "compact" : "standard" }).format(value);
}

export function plural(count: number, singular: string, pluralForm = `${singular}s`): string {
  return `${count} ${count === 1 ? singular : pluralForm}`;
}

const CATEGORY_LABELS: Record<string, string> = {
  documentation: "Documentation",
  entry_point: "Entry point",
  configuration: "Configuration",
  dependency: "Dependencies",
  core_logic: "Core logic",
  routes: "Routes",
  models: "Data models",
  database: "Database",
  ui: "User interface",
  template: "Template",
  test: "Tests",
  utility: "Utility",
  deployment: "Deployment",
  unknown: "Other",
};

export function categoryLabel(category: string): string {
  return CATEGORY_LABELS[category] ?? category.replace(/_/g, " ");
}

// --- sessionStorage (always optional: private windows and blocked storage must not break the page) ---

export function readSession<T>(key: string, isValid: (value: unknown) => value is T): T | null {
  try {
    const raw = window.sessionStorage.getItem(key);
    if (raw === null) return null;
    const parsed: unknown = JSON.parse(raw);
    return isValid(parsed) ? parsed : null;
  } catch {
    return null;
  }
}

export function writeSession(key: string, value: unknown): void {
  try {
    window.sessionStorage.setItem(key, JSON.stringify(value));
  } catch {
    // Storage full or unavailable: progress simply is not remembered.
  }
}

export function isNumberArray(value: unknown): value is number[] {
  return Array.isArray(value) && value.every((item) => typeof item === "number");
}

import type { AIExplanation, Analysis, ApiErrorBody, Health, QuestionAnswer } from "./types";

/**
 * Base URL for API requests.
 * - Production on Vercel: leave NEXT_PUBLIC_API_BASE_URL empty; the frontend and
 *   API share a domain, so requests go to relative /api/... paths.
 * - Local development: defaults to the FastAPI server on http://localhost:8000.
 */
const DEV_API_BASE_URL = "http://localhost:8000";

export function apiBaseUrl(): string {
  const configured = (process.env.NEXT_PUBLIC_API_BASE_URL ?? "").trim().replace(/\/+$/, "");
  if (configured) return configured;
  return process.env.NODE_ENV === "development" ? DEV_API_BASE_URL : "";
}

export class ApiError extends Error {
  readonly status: number;
  readonly code: string;
  readonly title: string;
  readonly details: ApiErrorBody["details"];

  constructor(status: number, body: ApiErrorBody) {
    super(body.message);
    this.name = "ApiError";
    this.status = status;
    this.code = body.code;
    this.title = body.title;
    this.details = body.details;
  }
}

const NETWORK_ERROR: ApiErrorBody = {
  code: "NETWORK_ERROR",
  title: "Could not reach RepoLens",
  message: "The RepoLens API did not respond. Check your connection and try again.",
  details: null,
};

const SERVER_UNAVAILABLE: ApiErrorBody = {
  code: "SERVER_UNAVAILABLE",
  title: "RepoLens is unavailable",
  message:
    "The server did not return a usable response. Very large repositories can take longer than the server allows.",
  details: null,
};

const BAD_RESPONSE: ApiErrorBody = {
  code: "BAD_RESPONSE",
  title: "Unexpected response",
  message: "The RepoLens API returned something it should not have. Please try again.",
  details: null,
};

function isErrorBody(value: unknown): value is { error: ApiErrorBody } {
  if (typeof value !== "object" || value === null || !("error" in value)) return false;
  const error = (value as { error: unknown }).error;
  return (
    typeof error === "object" &&
    error !== null &&
    typeof (error as ApiErrorBody).code === "string" &&
    typeof (error as ApiErrorBody).message === "string"
  );
}

async function request<T>(path: string, init: RequestInit = {}): Promise<T> {
  let response: Response;
  try {
    response = await fetch(`${apiBaseUrl()}${path}`, {
      ...init,
      headers: { "Content-Type": "application/json", ...init.headers },
      cache: "no-store",
    });
  } catch {
    throw new ApiError(0, NETWORK_ERROR);
  }

  let body: unknown;
  try {
    body = await response.json();
  } catch {
    throw new ApiError(response.status, response.ok ? BAD_RESPONSE : SERVER_UNAVAILABLE);
  }

  if (!response.ok) {
    throw new ApiError(response.status, isErrorBody(body) ? body.error : BAD_RESPONSE);
  }
  return body as T;
}

function post<T>(path: string, payload: object, signal?: AbortSignal): Promise<T> {
  return request<T>(path, { method: "POST", body: JSON.stringify(payload), signal });
}

export function getHealth(): Promise<Health> {
  return request<Health>("/api/health");
}

export function analyzeRepository(repoUrl: string, options: { refresh?: boolean; signal?: AbortSignal } = {}) {
  return post<Analysis>("/api/analyze", { repo_url: repoUrl, refresh: options.refresh ?? false }, options.signal);
}

export function askQuestion(analysisId: string, question: string) {
  return post<QuestionAnswer>("/api/question", { analysis_id: analysisId, question });
}

export function requestExplanation(analysisId: string) {
  return post<AIExplanation>("/api/explain", { analysis_id: analysisId });
}

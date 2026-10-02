"use client";

import { useRouter } from "next/navigation";
import { useId, useRef, useState, type FormEvent } from "react";
import { ArrowRight } from "lucide-react";
import { analyzeHref, canonicalRepositoryUrl, checkRepositoryUrl, cn, EXAMPLE_REPOSITORY } from "@/lib/utils";

export function RepositoryInput({ initialValue = "" }: { initialValue?: string }) {
  const router = useRouter();
  const inputRef = useRef<HTMLInputElement>(null);
  const inputId = useId();
  const errorId = useId();
  const helperId = useId();
  const [value, setValue] = useState(initialValue);
  const [error, setError] = useState<string | null>(null);
  const [pending, setPending] = useState(false);

  function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const check = checkRepositoryUrl(value);
    if (!check.ok) {
      setError(check.message);
      inputRef.current?.focus();
      return;
    }
    setError(null);
    setPending(true);
    router.push(analyzeHref(canonicalRepositoryUrl(check.owner, check.repo)));
  }

  function useExample() {
    setValue(EXAMPLE_REPOSITORY);
    setError(null);
    inputRef.current?.focus();
  }

  return (
    <form onSubmit={submit} noValidate className="w-full">
      <label htmlFor={inputId} className="mb-2 block text-[13px] font-medium text-muted">
        Public GitHub repository URL
      </label>
      <div className="flex flex-col gap-2 sm:flex-row">
        <input
          ref={inputRef}
          id={inputId}
          name="repo"
          type="text"
          inputMode="url"
          autoComplete="off"
          autoCapitalize="none"
          spellCheck={false}
          placeholder="https://github.com/owner/repository"
          value={value}
          onChange={(event) => {
            setValue(event.target.value);
            if (error) setError(null);
          }}
          aria-invalid={error ? true : undefined}
          aria-describedby={error ? `${errorId} ${helperId}` : helperId}
          className={cn(
            "h-11 min-w-0 flex-1 rounded-[10px] border bg-surface px-3.5 font-mono text-[14px] text-fg placeholder:text-faint",
            "transition-colors focus:border-accent focus:outline-none focus-visible:outline-none focus:ring-2 focus:ring-accent/25",
            error ? "border-rose/70" : "border-line-strong hover:border-faint/60",
          )}
        />
        <button
          type="submit"
          disabled={pending}
          className="inline-flex h-11 shrink-0 items-center justify-center gap-2 rounded-[10px] bg-fg px-5 text-[14px] font-medium text-bg transition-colors hover:bg-white disabled:opacity-70"
        >
          {pending ? "Opening…" : "Analyze repository"}
          {!pending && <ArrowRight aria-hidden="true" className="size-4" />}
        </button>
      </div>
      {error && (
        <p id={errorId} role="alert" className="mt-2 text-[13px] text-rose">
          {error}
        </p>
      )}
      <div className="mt-3 flex flex-col gap-1.5 text-[13px] text-faint sm:flex-row sm:items-center sm:justify-between">
        <p id={helperId}>Works with public Python repositories. Analysis is read-only.</p>
        <button
          type="button"
          onClick={useExample}
          className="self-start rounded-md text-left text-muted underline decoration-line-strong underline-offset-4 hover:text-fg hover:decoration-fg sm:self-auto"
        >
          Use example: <span className="font-mono">miguelgrinberg/microblog</span>
        </button>
      </div>
    </form>
  );
}

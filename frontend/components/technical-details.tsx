import type { ReactNode } from "react";
import { ChevronDown } from "lucide-react";
import type { Analysis } from "@/lib/types";
import { categoryLabel, plural } from "@/lib/utils";
import { InlineText } from "./inline-text";
import { SectionHeader } from "./section-header";

function Disclosure({ title, summary, children }: { title: string; summary: string; children: ReactNode }) {
  return (
    <details className="group border-b border-line">
      <summary className="flex cursor-pointer list-none items-center justify-between gap-4 py-4 select-none [&::-webkit-details-marker]:hidden">
        <span>
          <span className="text-[14px] text-fg">{title}</span>
          <span className="ml-3 text-[13px] text-faint">{summary}</span>
        </span>
        <ChevronDown
          aria-hidden="true"
          className="size-4 shrink-0 text-faint transition-transform group-open:rotate-180"
        />
      </summary>
      <div className="pb-5 text-[13.5px] leading-relaxed text-muted">{children}</div>
    </details>
  );
}

export function TechnicalDetails({ analysis }: { analysis: Analysis }) {
  const { dependencies, files_summary: files, framework, entry_point: entry } = analysis;
  const rateLimitNote = analysis.warnings.find((warning) => /rate limit/i.test(warning));

  return (
    <div className="space-y-6">
      <SectionHeader
        id="section-technical"
        title="Technical Details"
        description="The raw facts behind the analysis, for when you want to check RepoLens's work."
      />
      <div className="border-t border-line">
        <Disclosure title="Dependencies" summary={plural(dependencies.packages.length, "package")}>
          {dependencies.files.length === 0 ? (
            <p>No dependency file (requirements.txt, pyproject.toml, Pipfile, setup.cfg) was analysed.</p>
          ) : (
            <div className="space-y-4">
              {dependencies.files.map((file) => (
                <div key={file.path}>
                  <p className="font-mono text-[13px] text-fg">{file.path}</p>
                  <p className="mt-1 font-mono text-[12.5px] break-words text-faint">
                    {file.packages.length > 0 ? file.packages.join("  ") : "No packages could be parsed."}
                  </p>
                </div>
              ))}
            </div>
          )}
        </Disclosure>

        <Disclosure title="Analysed files" summary={`${files.analysed_python_files} Python files analysed`}>
          <dl className="grid max-w-md grid-cols-[1fr_auto] gap-x-6 gap-y-1">
            <dt>Files in the repository tree</dt>
            <dd className="font-mono text-fg tabular-nums">{files.tree_files}</dd>
            <dt>Files downloaded</dt>
            <dd className="font-mono text-fg tabular-nums">{files.downloaded_files}</dd>
            <dt>Python application files in the tree</dt>
            <dd className="font-mono text-fg tabular-nums">{files.python_files_in_tree}</dd>
            <dt>Python application files analysed</dt>
            <dd className="font-mono text-fg tabular-nums">{files.analysed_python_files}</dd>
            <dt>Files scored</dt>
            <dd className="font-mono text-fg tabular-nums">{files.scored_files}</dd>
          </dl>
          {Object.keys(files.by_category).length > 0 && (
            <p className="mt-4">
              By category:{" "}
              {Object.entries(files.by_category)
                .map(([category, count]) => `${categoryLabel(category)} ${count}`)
                .join(" · ")}
            </p>
          )}
        </Disclosure>

        <Disclosure title="Skipped files and folders" summary={plural(analysis.skip_for_now.length, "item")}>
          {analysis.skip_for_now.length === 0 ? (
            <p>Nothing obvious to skip. This repository is already small and focused.</p>
          ) : (
            <ul className="space-y-2">
              {analysis.skip_for_now.map((item) => (
                <li key={item.path}>
                  <span className="font-mono text-[13px] text-fg">{item.path}</span>
                  <span className="text-faint"> — {item.reason}</span>
                </li>
              ))}
            </ul>
          )}
        </Disclosure>

        <Disclosure title="Detection rules and evidence" summary={framework.name}>
          <p className="text-fg">Framework: {framework.name} ({framework.confidence.toLowerCase()} confidence)</p>
          <ul className="mt-1 list-disc space-y-0.5 pl-5">
            {framework.evidence.map((item) => (
              <li key={item}>
                <InlineText text={item} />
              </li>
            ))}
          </ul>
          <p className="mt-3">
            Framework evidence is scored from dependency files, imports found by Python&apos;s <code>ast</code>{" "}
            module, and framework start-up calls such as <code className="font-mono">Flask(...)</code>.
          </p>
          {entry && (
            <>
              <p className="mt-4 text-fg">
                Entry point: <span className="font-mono">{entry.path}</span>
              </p>
              <ul className="mt-1 list-disc space-y-0.5 pl-5">
                {entry.reasons.map((reason) => (
                  <li key={reason}>
                    <InlineText text={reason} />
                  </li>
                ))}
              </ul>
            </>
          )}
        </Disclosure>

        <Disclosure title="Warnings and limitations" summary={plural(analysis.warnings.length, "warning")}>
          {rateLimitNote && <p className="mb-3 text-amber">{rateLimitNote}</p>}
          {analysis.warnings.length > 0 && (
            <ul className="mb-4 list-disc space-y-1 pl-5">
              {analysis.warnings.map((warning) => (
                <li key={warning}>
                  <InlineText text={warning} />
                </li>
              ))}
            </ul>
          )}
          <ul className="list-disc space-y-1 pl-5 text-faint">
            {analysis.limitations.map((limitation) => (
              <li key={limitation}>{limitation}</li>
            ))}
            <li>
              Analysis results are kept only in this browser tab. The server keeps a short-lived copy in memory that
              may disappear at any time.
            </li>
          </ul>
        </Disclosure>
      </div>
    </div>
  );
}

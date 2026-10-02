"use client";

import { useId, useState } from "react";
import type { Citation } from "@/lib/types";
import { cn, formatLineRange } from "@/lib/utils";

function CitationLabel({ citation }: { citation: Citation }) {
  return (
    <>
      <span className="text-fg">{citation.path}</span>
      <span className="text-faint"> · {formatLineRange(citation.start_line, citation.end_line)}</span>
    </>
  );
}

/**
 * `app.py · lines 8–31`. When the API sent the cited source, the citation is a
 * button that reveals a read-only preview; otherwise it is plain text.
 */
export function SourceCitation({ citation }: { citation: Citation }) {
  const [open, setOpen] = useState(false);
  const previewId = useId();
  const base = "inline-flex max-w-full items-center gap-1 font-mono text-[12.5px] leading-6 break-all";

  if (!citation.preview || citation.preview.lines.length === 0) {
    return (
      <span className={cn(base, "text-muted")}>
        <CitationLabel citation={citation} />
      </span>
    );
  }

  const { preview } = citation;
  return (
    <div className="min-w-0">
      <button
        type="button"
        onClick={() => setOpen((value) => !value)}
        aria-expanded={open}
        aria-controls={previewId}
        className={cn(
          base,
          "rounded-md px-1 -mx-1 text-left underline decoration-line-strong decoration-dotted underline-offset-4 hover:bg-raised hover:decoration-accent",
        )}
      >
        <CitationLabel citation={citation} />
        <span className="sr-only">{open ? "Hide source" : "Show source"}</span>
      </button>
      {open && (
        <div
          id={previewId}
          className="scroll-thin mt-2 overflow-x-auto rounded-[10px] border border-line bg-bg"
        >
          <pre className="py-3 font-mono text-[12.5px] leading-[1.7]">
            {preview.lines.map((line, index) => (
              <div key={index} className="flex">
                <span
                  aria-hidden="true"
                  className="w-12 shrink-0 select-none pr-4 text-right text-faint"
                >
                  {preview.start_line + index}
                </span>
                <code className="pr-4 whitespace-pre text-fg/90">{line || " "}</code>
              </div>
            ))}
          </pre>
          {preview.truncated && (
            <p className="border-t border-line px-4 py-2 text-xs text-faint">
              Preview shortened. The full range continues in the repository.
            </p>
          )}
        </div>
      )}
    </div>
  );
}

export function CitationList({ citations, label = "Evidence" }: { citations: Citation[]; label?: string }) {
  if (citations.length === 0) return null;
  return (
    <div className="mt-3">
      <p className="text-[11px] font-medium tracking-[0.08em] text-faint uppercase">{label}</p>
      <ul className="mt-1 space-y-0.5">
        {citations.map((citation) => (
          <li key={`${citation.path}:${citation.start_line}-${citation.end_line}`}>
            <SourceCitation citation={citation} />
          </li>
        ))}
      </ul>
    </div>
  );
}

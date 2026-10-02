import type { ReactNode } from "react";

/** Shown when a section has no evidence to display. It explains why instead of inventing content. */
export function EmptyState({ title, children }: { title: string; children: ReactNode }) {
  return (
    <div className="rounded-[12px] border border-dashed border-line-strong px-5 py-8 text-center sm:px-8">
      <p className="text-[15px] font-medium text-fg">{title}</p>
      <div className="mx-auto mt-2 max-w-md text-[14px] leading-relaxed text-muted">{children}</div>
    </div>
  );
}

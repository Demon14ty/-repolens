import type { ReactNode } from "react";

/** Heading for one analysis section. The heading can receive focus when the section changes. */
export function SectionHeader({
  id,
  title,
  description,
  aside,
}: {
  id: string;
  title: string;
  description?: ReactNode;
  aside?: ReactNode;
}) {
  return (
    <div className="flex flex-col gap-3 border-b border-line pb-5 sm:flex-row sm:items-end sm:justify-between">
      <div className="min-w-0">
        <h2 id={id} tabIndex={-1} className="text-[22px] font-semibold tracking-[-0.01em] text-fg focus:outline-none">
          {title}
        </h2>
        {description && <p className="mt-1.5 max-w-2xl text-[14px] leading-relaxed text-muted">{description}</p>}
      </div>
      {aside && <div className="shrink-0">{aside}</div>}
    </div>
  );
}

/** Small uppercase label used for sub-sections such as "Evidence" or "Strengths". */
export function Eyebrow({ children, as: Tag = "h3" }: { children: ReactNode; as?: "h3" | "h4" | "p" }) {
  return <Tag className="text-[11px] font-medium tracking-[0.08em] text-faint uppercase">{children}</Tag>;
}

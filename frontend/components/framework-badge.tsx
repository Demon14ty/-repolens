import { cn } from "@/lib/utils";

/** Compact label for the detected framework or language, e.g. "Flask" or "Python". */
export function FrameworkBadge({ name, className }: { name: string; className?: string }) {
  const short = name.replace(/\s*\(.*\)\s*$/, "");
  return (
    <span
      className={cn(
        "inline-flex items-center rounded-md border border-line bg-raised px-2 py-0.5 font-mono text-xs text-muted",
        className,
      )}
    >
      {short}
    </span>
  );
}

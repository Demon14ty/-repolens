import { Fragment } from "react";

const TOKEN = /(`[^`\n]+`|\*\*[^*\n]+\*\*)/g;

/**
 * Renders the small amount of inline markup the analysis produces:
 * `code` spans and **bold** text. Everything else is plain text (React escapes it).
 */
export function InlineText({ text }: { text: string }) {
  const parts = text.split(TOKEN);
  return (
    <>
      {parts.map((part, index) => {
        if (part.startsWith("`") && part.endsWith("`") && part.length > 2) {
          return (
            <code
              key={index}
              className="rounded-[5px] border border-line bg-raised px-1 py-px font-mono text-[0.88em] text-fg break-words"
            >
              {part.slice(1, -1)}
            </code>
          );
        }
        if (part.startsWith("**") && part.endsWith("**") && part.length > 4) {
          return (
            <strong key={index} className="font-semibold text-fg">
              {part.slice(2, -2)}
            </strong>
          );
        }
        return <Fragment key={index}>{part}</Fragment>;
      })}
    </>
  );
}

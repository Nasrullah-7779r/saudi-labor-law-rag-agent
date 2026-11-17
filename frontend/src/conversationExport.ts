import { copy } from "./copy";
import { SOURCE_URL } from "./law";
import { isNarration } from "./narration";
import type { Language, LawMessage } from "./types";

const quote = (text: string) =>
  text
    .trim()
    .split("\n")
    .map((line) => `> ${line}`)
    .join("\n");

/** The finished conversation as Markdown: answers without narration, plus each cited article. */
export function conversationToMarkdown(
  messages: LawMessage[],
  language: Language,
  exportedAt: Date,
): string {
  const t = copy[language];
  const sections = messages.map((message) => {
    const isUser = message.role === "user";
    const lines = [`### ${isUser ? t.you : t.assistant}`];
    message.parts.forEach((part, index) => {
      if (part.type === "text") {
        if (!isUser && isNarration(message.parts, index, false)) return;
        lines.push(part.text.trim());
      } else if (part.type === "data-citations" && part.data.citations.length) {
        lines.push(`**${t.sources}**`);
        for (const citation of part.data.citations)
          lines.push(`**${t.article} ${citation.article_no}**\n\n${quote(citation.excerpt)}`);
      }
    });
    return lines.join("\n\n");
  });
  const header = [
    `# ${t.title}`,
    `${t.exportedOn} ${exportedAt.toISOString().slice(0, 10)} · [${t.official}](${SOURCE_URL})`,
    `> ${t.legal}`,
  ].join("\n\n");
  return [header, ...sections].join("\n\n---\n\n") + "\n";
}

/** Saves ``markdown`` as a file through a temporary object-URL link. */
export function downloadMarkdown(filename: string, markdown: string): void {
  const url = URL.createObjectURL(
    new Blob([markdown], { type: "text/markdown;charset=utf-8" }),
  );
  const link = document.createElement("a");
  link.href = url;
  link.download = filename;
  link.click();
  URL.revokeObjectURL(url);
}

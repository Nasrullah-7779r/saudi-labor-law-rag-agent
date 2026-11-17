import Markdown, { type Components } from "react-markdown";
import remarkGfm from "remark-gfm";
import { copy } from "./copy";
import { isNarration } from "./narration";
import type { Language, LawMessage } from "./types";

// Model output is untrusted: raw HTML is skipped (no rehype-raw) and
// react-markdown's defaultUrlTransform strips unsafe URL schemes.
// Links open in a new tab without opener access.
// Docs: https://github.com/remarkjs/react-markdown#options (v10.1.0)
const markdownComponents: Components = {
  a({ node: _node, ...props }) {
    return <a {...props} target="_blank" rel="noopener noreferrer" />;
  },
};

export function Answer({
  message,
  language,
  streaming,
}: {
  message: LawMessage;
  language: Language;
  streaming: boolean;
}) {
  const t = copy[language];
  return (
    <article className={`message ${message.role}`}>
      <div className="speaker">
        {message.role === "user" ? t.you : t.assistant}
      </div>
      {message.parts.map((part, index) => {
        if (part.type === "text") {
          // Narration is an assistant concept; the user's question always shows.
          if (
            message.role === "assistant" &&
            isNarration(message.parts, index, streaming)
          )
            return null;
          return (
            <div className="answer-text" dir="auto" key={index}>
              <Markdown
                remarkPlugins={[remarkGfm]}
                components={markdownComponents}
                skipHtml
              >
                {part.text}
              </Markdown>
            </div>
          );
        }
        if (part.type === "data-citations")
          return (
            <div className="citations" key={index}>
              <p className="citation-label">{t.sources}</p>
              <div className="citation-list">
                {part.data.citations.map((citation, i) => (
                  <details
                    className="citation"
                    key={`${citation.article_no}-${i}`}
                  >
                    <summary>
                      {t.article} {citation.article_no}
                    </summary>
                    <blockquote dir="auto">{citation.excerpt}</blockquote>
                  </details>
                ))}
              </div>
            </div>
          );
        return null;
      })}
    </article>
  );
}

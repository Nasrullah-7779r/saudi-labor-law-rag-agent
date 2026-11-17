import { useChat } from "@ai-sdk/react";
import { useEffect, useMemo, useRef, useState } from "react";
import { createRoot } from "react-dom/client";
import Markdown, { type Components } from "react-markdown";
import remarkGfm from "remark-gfm";
import { copy } from "./copy";
import { createLawTransport } from "./transport";
import type { Language, LawMessage } from "./types";
import "./styles.css";

// Model output is untrusted: raw HTML is skipped (no rehype-raw) and
// react-markdown's defaultUrlTransform strips unsafe URL schemes.
// Links open in a new tab without opener access.
// Docs: https://github.com/remarkjs/react-markdown#options (v10.1.0)
const markdownComponents: Components = {
  a({ node: _node, ...props }) {
    return <a {...props} target="_blank" rel="noopener noreferrer" />;
  },
};

const SOURCE_URL =
  "https://laws.boe.gov.sa/BoeLaws/Laws/LawDetails/08381293-6388-48e2-8ad2-a9a700f2aa94/1";

const MAX_STATUS_ARTICLES = 3;

// Text the model writes before a tool call ("I need to check…") is narration, not answer.
// Hide a text part once a tool status follows it; while streaming, also hide text that no
// tool status precedes yet, since it may still turn out to be narration. A reply that never
// calls a tool then appears when the stream ends.
function isNarration(
  parts: LawMessage["parts"],
  index: number,
  streaming: boolean,
): boolean {
  const isStatus = (part: LawMessage["parts"][number]) =>
    part.type === "data-tool-status";
  if (parts.slice(index + 1).some(isStatus)) return true;
  return streaming && !parts.slice(0, index).some(isStatus);
}

function Answer({
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

function Conversation({
  language,
  remaining,
  onUsage,
}: {
  language: Language;
  remaining: number | null;
  onUsage: (value: number) => void;
}) {
  const t = copy[language];
  const thread = useRef<string | null>(null);
  const transport = useMemo(() => createLawTransport(thread), []);
  const [input, setInput] = useState("");
  const lastQuestion = useRef("");
  const bottom = useRef<HTMLDivElement>(null);
  const {
    messages,
    sendMessage,
    status,
    stop,
    error,
    clearError,
    setMessages,
  } = useChat<LawMessage>({
    transport,
    onData: (part) => {
      if (part.type === "data-usage") onUsage(part.data.remaining_questions);
    },
  });
  useEffect(
    () => () => {
      void stop();
    },
    [stop],
  );
  const busy = status === "submitted" || status === "streaming";
  const lastMessage = messages.at(-1);
  const tool =
    lastMessage?.role === "assistant"
      ? lastMessage.parts
          .filter((part) => part.type === "data-tool-status")
          .at(-1)
      : undefined;
  const readingArticles = tool?.data.article_nos?.slice(0, MAX_STATUS_ARTICLES);
  const progress =
    tool?.data.state === "running"
      ? tool.data.tool === "calc_end_of_service"
        ? t.calculating
        : t.searching
      : readingArticles?.length
        ? t.reading(readingArticles)
        : t.thinking;
  const errorKey = error?.message;
  const errorText =
    errorKey &&
    errorKey in t &&
    typeof t[errorKey as keyof typeof t] === "string"
      ? String(t[errorKey as keyof typeof t])
      : t.unavailable;

  useEffect(() => {
    const end = bottom.current;
    if (
      end &&
      window.innerHeight + window.scrollY >= document.body.scrollHeight - 400
    ) {
      end.scrollIntoView({ behavior: "instant", block: "end" });
    }
  }, [messages, busy]);

  function ask(text: string) {
    const question = text.trim();
    if (!question || question.length > 2000 || busy) return;
    clearError();
    lastQuestion.current = question;
    setInput("");
    void sendMessage({ text: question });
  }

  function retry() {
    // Drop the failed turn before resending so the transcript has one copy.
    const userIndex = messages.findLastIndex(
      (message) => message.role === "user",
    );
    setMessages(messages.slice(0, Math.max(userIndex, 0)));
    ask(lastQuestion.current);
  }

  return (
    <>
      <section className="conversation" aria-label={t.title}>
        {messages.length === 0 ? (
          <div className="welcome">
            <div className="law-mark" aria-hidden="true">
              §
            </div>
            <h1>{t.intro}</h1>
            <p>{t.description}</p>
            <div className="starters">
              {t.starters.map((question) => (
                <button key={question} onClick={() => ask(question)}>
                  {question}
                  <span aria-hidden="true">↗</span>
                </button>
              ))}
            </div>
          </div>
        ) : (
          <div
            className="transcript"
            aria-live="polite"
            aria-relevant="additions text"
          >
            {messages.map((message) => (
              <Answer
                key={message.id}
                message={message}
                language={language}
                streaming={busy && message.id === lastMessage?.id}
              />
            ))}
          </div>
        )}
        {busy && (
          <p className="progress" role="status">
            <span className="status-dot" />
            {progress}
          </p>
        )}
        {error && (
          <div className="error" role="alert">
            <p>{errorText}</p>
            {errorKey !== "ip_quota" && errorKey !== "global_budget" && (
              <button onClick={retry}>{t.retry}</button>
            )}
          </div>
        )}
        <div ref={bottom} />
      </section>
      <div className="composer-wrap">
        <div className="quota" title={t.reset} role="status">
          {remaining === null ? (
            t.quotaUnknown
          ) : (
            <>
              <strong>{remaining}</strong> {t.quota}
            </>
          )}
        </div>
        <form
          className="composer"
          onSubmit={(event) => {
            event.preventDefault();
            ask(input);
          }}
        >
          <label className="sr-only" htmlFor="question">
            {t.inputLabel}
          </label>
          <textarea
            id="question"
            dir="auto"
            value={input}
            maxLength={2000}
            rows={2}
            placeholder={t.placeholder}
            onChange={(event) => setInput(event.target.value)}
            onKeyDown={(event) => {
              if (
                event.key === "Enter" &&
                !event.shiftKey &&
                !event.nativeEvent.isComposing
              ) {
                event.preventDefault();
                ask(input);
              }
            }}
          />
          <div className="composer-actions">
            <span>
              {input.length}/2000{" "}
              <span className="sr-only">{t.characters}</span>
            </span>
            {busy ? (
              <button type="button" onClick={() => void stop()}>
                {t.stop} <span aria-hidden="true">■</span>
              </button>
            ) : (
              <button disabled={!input.trim()} type="submit">
                {t.send} <span aria-hidden="true">↑</span>
              </button>
            )}
          </div>
        </form>
        <p className="logging">{t.logging}</p>
      </div>
    </>
  );
}

function App() {
  const [language, setLanguage] = useState<Language>("en");
  const [conversation, setConversation] = useState(0);
  const [remaining, setRemaining] = useState<number | null>(null);
  const t = copy[language];
  useEffect(() => {
    document.documentElement.lang = language;
    document.documentElement.dir = language === "ar" ? "rtl" : "ltr";
  }, [language]);
  return (
    <div className="app-shell">
      <aside className="sidebar">
        <a href="/" className="brand">
          <span className="brand-icon" aria-hidden="true">
            §
          </span>
          <span>
            {t.title}
            <small>
              {language === "en" ? "نظام العمل السعودي" : "Saudi Labor Law"}
            </small>
          </span>
        </a>
        <p className="tagline">{t.subtitle}</p>
        <button
          className="new-chat"
          onClick={() => setConversation((value) => value + 1)}
        >
          <span aria-hidden="true">＋</span>
          {t.newChat}
        </button>
        <div className="sidebar-bottom">
          <p>{t.demo}</p>
          <p className="legal">{t.legal}</p>
          <a href={SOURCE_URL} target="_blank" rel="noreferrer">
            {t.official} ↗
          </a>
        </div>
      </aside>
      <main>
        <header className="topbar">
          <span>{t.title}</span>
          <button
            className="language"
            onClick={() => setLanguage(language === "en" ? "ar" : "en")}
            lang={language === "en" ? "ar" : "en"}
          >
            {language === "en" ? "العربية" : "English"}
          </button>
        </header>
        <Conversation
          key={conversation}
          language={language}
          remaining={remaining}
          onUsage={setRemaining}
        />
        <footer className="mobile-legal">{t.legal}</footer>
      </main>
    </div>
  );
}

createRoot(document.getElementById("root")!).render(<App />);

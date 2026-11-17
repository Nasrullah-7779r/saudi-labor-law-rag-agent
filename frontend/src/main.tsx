import { useChat } from "@ai-sdk/react";
import { useEffect, useMemo, useRef, useState } from "react";
import { createRoot } from "react-dom/client";
import { Answer } from "./Answer";
import { conversationToMarkdown, downloadMarkdown } from "./conversationExport";
import { copy } from "./copy";
import { SOURCE_URL } from "./law";
import { createLawTransport } from "./transport";
import type { Language, LawMessage } from "./types";
import "./styles.css";

const MAX_STATUS_ARTICLES = 3;

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

  function exportConversation() {
    const now = new Date();
    downloadMarkdown(
      `saudi-labor-law-${now.toISOString().slice(0, 10)}.md`,
      conversationToMarkdown(messages, language, now),
    );
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
          {messages.length > 0 && !busy && (
            <button type="button" className="export" onClick={exportConversation}>
              {t.export} <span aria-hidden="true">↓</span>
            </button>
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

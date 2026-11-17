import { describe, expect, it } from "vitest";
import { conversationToMarkdown } from "./conversationExport";
import { copy } from "./copy";
import { SOURCE_URL } from "./law";
import type { LawMessage } from "./types";

const exportedAt = new Date("2026-03-14T10:20:30Z");

const user = (text: string): LawMessage => ({
  id: "u1",
  role: "user",
  parts: [{ type: "text", text }],
});

describe("conversationToMarkdown", () => {
  it("starts with the title, ISO date, official source link and legal disclaimer", () => {
    const md = conversationToMarkdown([user("Q")], "en", exportedAt);

    expect(md).toContain(`# ${copy.en.title}`);
    expect(md).toContain("2026-03-14");
    expect(md).toContain(`[${copy.en.official}](${SOURCE_URL})`);
    expect(md).toContain(copy.en.legal);
  });

  it("puts the question under You and the answer under Labor Law assistant", () => {
    const messages: LawMessage[] = [
      user("How much leave do I get?"),
      {
        id: "a1",
        role: "assistant",
        parts: [{ type: "text", text: "Thirty days of leave." }],
      },
    ];

    const md = conversationToMarkdown(messages, "en", exportedAt);

    expect(md).toContain("### You\n\nHow much leave do I get?");
    expect(md).toContain("### Labor Law assistant\n\nThirty days of leave.");
  });

  it("drops narration before a tool status, keeps the final answer and user text", () => {
    const messages: LawMessage[] = [
      user("Question before tool status"),
      {
        id: "a1",
        role: "assistant",
        parts: [
          { type: "text", text: "Let me check the law." },
          {
            type: "data-tool-status",
            data: { tool: "search_labor_law", state: "done" },
          },
          { type: "text", text: "The final answer." },
        ],
      },
    ];

    const md = conversationToMarkdown(messages, "en", exportedAt);

    expect(md).not.toContain("Let me check the law.");
    expect(md).toContain("The final answer.");
    expect(md).toContain("Question before tool status");
  });

  it("keeps user text even when a tool status follows it", () => {
    const userWithStatus: LawMessage = {
      id: "u1",
      role: "user",
      parts: [
        { type: "text", text: "User text kept" },
        {
          type: "data-tool-status",
          data: { tool: "search_labor_law", state: "done" },
        },
      ],
    };

    const md = conversationToMarkdown([userWithStatus], "en", exportedAt);

    expect(md).toContain("User text kept");
  });

  it("renders citations as Article n with every excerpt line blockquoted", () => {
    const messages: LawMessage[] = [
      {
        id: "a1",
        role: "assistant",
        parts: [
          { type: "text", text: "Answer." },
          {
            type: "data-citations",
            data: {
              citations: [
                { article_no: 109, excerpt: "line one\nline two" },
                { article_no: 84, excerpt: "single" },
              ],
            },
          },
        ],
      },
    ];

    const md = conversationToMarkdown(messages, "en", exportedAt);

    expect(md).toContain("Article 109");
    expect(md).toContain("> line one\n> line two");
    expect(md).toContain("Article 84");
    expect(md).toContain("> single");
  });

  it("uses Arabic labels for the Arabic language", () => {
    const messages: LawMessage[] = [
      user("سؤال"),
      {
        id: "a1",
        role: "assistant",
        parts: [
          { type: "text", text: "جواب" },
          {
            type: "data-citations",
            data: { citations: [{ article_no: 109, excerpt: "نص" }] },
          },
        ],
      },
    ];

    const md = conversationToMarkdown(messages, "ar", exportedAt);

    expect(md).toContain("### أنت");
    expect(md).toContain("المادة 109");
    expect(md).not.toContain("### You");
    expect(md).not.toContain("Article 109");
  });
});

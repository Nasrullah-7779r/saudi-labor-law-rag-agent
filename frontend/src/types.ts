import type { UIMessage } from "ai";

// Wire shapes owned by backend/src/labor_law_agent/stream_events.py; keep in sync.
export type Citation = { article_no: number; excerpt: string };
export type ToolStatus = {
  tool: "search_labor_law" | "calc_end_of_service";
  state: "running" | "done";
};
export type Usage = {
  input_tokens: number;
  output_tokens: number;
  remaining_questions: number;
};
export type LawMessage = UIMessage<
  unknown,
  {
    "tool-status": ToolStatus;
    citations: { citations: Citation[] };
    usage: Usage;
  }
>;
export type Language = "en" | "ar";

import type { LawMessage } from "./types";

// Text the model writes before a tool call ("I need to check…") is narration, not answer.
// Hide a text part once a tool status follows it; while streaming, also hide text that no
// tool status precedes yet, since it may still turn out to be narration. A reply that never
// calls a tool then appears when the stream ends.
export function isNarration(
  parts: LawMessage["parts"],
  index: number,
  streaming: boolean,
): boolean {
  const isStatus = (part: LawMessage["parts"][number]) =>
    part.type === "data-tool-status";
  if (parts.slice(index + 1).some(isStatus)) return true;
  return streaming && !parts.slice(0, index).some(isStatus);
}

import { DefaultChatTransport } from "ai";
import type { LawMessage } from "./types";

// AI SDK 7: documented request transform + fetch middleware, consuming Python's
// UI-message SSE v1 directly. https://ai-sdk.dev/docs/ai-sdk-ui/transport
export function createLawTransport(thread: { current: string | null }) {
  return new DefaultChatTransport<LawMessage>({
    api: `${(import.meta.env.VITE_API_URL || "http://127.0.0.1:8000").replace(/\/$/, "")}/chat`,
    prepareSendMessagesRequest: ({ messages }) => ({
      body: {
        message:
          messages
            .at(-1)
            ?.parts.filter((part) => part.type === "text")
            .map((part) => part.text)
            .join("") || "",
        ...(thread.current ? { thread_id: thread.current } : {}),
      },
    }),
    fetch: async (input, init) => {
      const response = await fetch(input, init);
      if (!response.ok) {
        if (response.status === 429) {
          const body: unknown = await response.json().catch(() => null);
          if (
            body &&
            typeof body === "object" &&
            "error" in body &&
            (body.error === "ip_quota" || body.error === "global_budget")
          ) {
            throw new Error(body.error);
          }
          throw new Error("throttled");
        }
        throw new Error(
          response.status === 422 ? "invalid_input" : "unavailable",
        );
      }
      thread.current = response.headers.get("X-Thread-Id") || thread.current;
      return response;
    },
  });
}

# `POST /chat` stream protocol

`POST /chat` streams one assistant message as Server-Sent Events in the
[AI SDK UI message stream protocol](https://ai-sdk.dev/docs/ai-sdk-ui/stream-protocol)
(v1), so an AI SDK UI frontend can consume it as a custom backend. The UI ticket
must confirm this choice against the chat UI library it picks. If it picks a
different library, change the encoder in `backend/src/labor_law_agent/stream_events.py`.
The event models are the contract.

## Request

```json
{ "message": "string, 1..2000 chars", "thread_id": "optional string, 1..128 chars" }
```

Invalid input → `422` (FastAPI validation body), no stream.

## Response

- `200`, `Content-Type: text/event-stream`
- `x-vercel-ai-ui-message-stream: v1`
- `X-Thread-Id`: the request's `thread_id`, or a new one when it was omitted. Send it back on follow-ups.

Each event is `data: <json>\n\n`. The stream ends with `data: [DONE]`.

| `type` | Payload | When |
| --- | --- | --- |
| `start` | `messageId` | first |
| `data-tool-status` | `data: {tool: "search_labor_law" \| "calc_end_of_service", state: "running" \| "done"}` | around each tool call |
| `text-start` / `text-delta` / `text-end` | `id`, `delta` (delta only) | answer text; concatenate the deltas that share an `id`. One text part per model turn, so text written before a tool call gets its own `id` |
| `data-citations` | `data: {citations: [{article_no: int, excerpt: str}]}` | after the text; retrieved articles the answer names ("Article N" / "المادة N"), best match first. Omitted when none |
| `data-usage` | `data: {input_tokens, output_tokens, remaining_questions}` | before `finish`; tokens summed over the turn's model calls. `remaining_questions` is `0` until the usage guard (#6) |
| `error` | `errorText` | a failure after streaming began (the status is already 200) |
| `finish` | — | last JSON event, also after `error` |

Example (stub reply, abridged):

```
data: {"type":"start","messageId":"msg-3f…"}
data: {"type":"data-tool-status","data":{"tool":"search_labor_law","state":"running"}}
data: {"type":"data-tool-status","data":{"tool":"search_labor_law","state":"done"}}
data: {"type":"text-start","id":"text-1"}
data: {"type":"text-delta","id":"text-1","delta":"This"}
data: {"type":"text-delta","id":"text-1","delta":" is"}
data: {"type":"text-end","id":"text-1"}
data: {"type":"data-citations","data":{"citations":[{"article_no":1,"excerpt":"(stub excerpt)"}]}}
data: {"type":"data-usage","data":{"input_tokens":0,"output_tokens":0,"remaining_questions":0}}
data: {"type":"finish"}
data: [DONE]
```

Quota rejections (`429` with `ip_quota` | `global_budget`) arrive with the usage-guard ticket.

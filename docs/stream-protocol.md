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
- `X-Thread-Id`: the request's `thread_id`, or a new one when it was omitted. Send it back on follow-ups; cross-turn memory remains #7, so current requests must be self-contained.

Each event is `data: <json>\n\n`. The stream ends with `data: [DONE]`.

| `type` | Payload | When |
| --- | --- | --- |
| `start` | `messageId` | first |
| `data-tool-status` | `data: {tool: "search_labor_law" \| "calc_end_of_service", state: "running" \| "done", article_nos: int[] \| null}` | around each tool call. `article_nos`: on a finished search, the retrieved article numbers, best match first; otherwise `null` |
| `text-start` / `text-delta` / `text-end` | `id`, `delta` (delta only) | answer text; concatenate the deltas that share an `id`. One text part per model turn, so text written before a tool call gets its own `id`. That pre-tool text is narration: it is not matched for citations, and the UI hides it |
| `data-citations` | `data: {citations: [{article_no: int, excerpt: str}]}` | after the text; retrieved articles the answer names ("Article N" / "المادة N"), best match first. Omitted when none |
| `data-usage` | `data: {input_tokens, output_tokens, remaining_questions}` | before `finish`; tokens summed over the turn's model calls. `remaining_questions`: questions left today for the caller's IP (`0` when quotas are off) |
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

## Quota rejections

Checked before any model call. Over a limit → `429`, JSON, no stream:

```json
{ "error": "ip_quota" }
```

- `ip_quota`: the caller's IP (API Gateway `requestContext.identity.sourceIp`; `X-Forwarded-For` is ignored) used its daily questions.
- `global_budget`: the demo's daily token budget is spent. Soft cap: usage is recorded after each turn, so concurrent turns can overshoot it.

Days are UTC.

## Frontend adapter

The Vite/React frontend pins AI SDK 7 (`@ai-sdk/react` 4). Its documented
`DefaultChatTransport.prepareSendMessagesRequest` sends the latest user text as
`message` instead of the SDK's default `messages` array. Fetch middleware retains
`X-Thread-Id` for follow-ups and maps typed JSON 429 responses to friendly copy.
`useChat<LawMessage>` consumes this existing SSE v1 stream without an encoder change.
Typed custom parts mirror the Python models in `frontend/src/types.ts`.

The browser calls API Gateway directly, so the trusted source-IP quota remains
per viewer. FastAPI CORS allows only the configured frontend origin in production
and exposes `X-Thread-Id`; the stub permits the two local Vite origins.
REST `AWS_PROXY` streaming requires this backend CORS ownership. Gateway Responses
separately add the same origin for API Gateway-owned 4xx/5xx errors (such as stage
throttling), so browsers can read their native status codes. Limits use
UTC days. A usage event with `remaining_questions: 0` means zero in the current
contract; stub quotas are disabled and also return zero (see README).

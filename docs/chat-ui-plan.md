# Public chat UI (#9)

```
Browser ── HTTPS ── CloudFront ── OAC/SigV4 ── private S3 (Vite/React)
    └── direct POST /chat ── API Gateway ── Lambda/FastAPI
           AI SDK UI-message SSE v1 ◀── text/status/citations/quota
GitHub main ── build backend + UI ── Terraform apply ── S3 upload ── invalidate
```

Use AI SDK 7.0.173 / React adapter 4.0.177: `DefaultChatTransport`, request transform
from latest user text to `{message, thread_id?}`, fetch middleware reads `X-Thread-Id`
and translates typed quota rejections. Custom typed data parts retain the existing
backend wire contract. New conversation remounts client state and discards the thread.
API calls go directly to API Gateway: routing through CloudFront would change the
trusted source IP seen by the existing quota guard. CORS permits only the frontend
origin in production and exposes the thread header. Local stub permits localhost Vite.
The current REST `AWS_PROXY` streaming integration requires backend CORS on backend
responses; HTTP API-style centralized CORS is unavailable here. Gateway Responses
add the same allowed origin to API Gateway-owned 4xx/5xx errors (including stage
throttling), preserving status codes so browser error handling remains readable.
This is split response ownership, not duplicate CORS middleware.

Design: public legal reference desk, not a dashboard. Deep green #134f46 sidebar,
ink #17332f, mist #f4f8f8, white #ffffff, line #c3d8d0, quiet blue-green #1a8e9a focus.
Segoe UI/Tahoma for legible bilingual text; Georgia only for the section symbol.
A single quiet arch-shaped legal mark gives the opening screen a recognizable cue.
Reading column aligned to the active language; source excerpts expand inline.
On mobile the sidebar becomes a compact masthead. No card grid or marketing hero.

Existing deployment workflow owns infrastructure and OIDC authentication; extend it
rather than introduce a competing deploy role/workflow. Build before deploy; upload
hashed assets before index.html; invalidate after both. Keep old hashed assets for
in-flight clients. Private S3 bucket uses account+region suffix, public access block,
owner-enforced ownership and an OAC-only bucket policy scoped to the distribution.
No new Lambda or runtime IAM permission needed.

## Verified official references

- [AI SDK transport](https://ai-sdk.dev/docs/ai-sdk-ui/transport), [useChat](https://ai-sdk.dev/docs/reference/ai-sdk-ui/use-chat), [custom data](https://ai-sdk.dev/docs/ai-sdk-ui/streaming-data), [SSE v1](https://ai-sdk.dev/docs/ai-sdk-ui/stream-protocol).
- React 19.3 [createRoot](https://react.dev/reference/react-dom/client/createRoot) and hooks reference; Vite 8 [guide](https://vite.dev/guide/) and [build-time environment](https://vite.dev/guide/env-and-mode). Node >=22.12; CI Node 24.
- AWS [REST proxy CORS](https://docs.aws.amazon.com/apigateway/latest/developerguide/how-to-cors.html), [streaming constraints](https://docs.aws.amazon.com/apigateway/latest/developerguide/response-transfer-mode.html), provider 6.x [Gateway Response schema](https://raw.githubusercontent.com/hashicorp/terraform-provider-aws/v6.0.0/website/docs/r/api_gateway_gateway_response.html.markdown).
- FastAPI 0.162 [CORSMiddleware](https://fastapi.tiangolo.com/tutorial/cors/) (`allow_origins`, methods, headers, `expose_headers`).
- Terraform AWS provider 6.x: [distribution](https://raw.githubusercontent.com/hashicorp/terraform-provider-aws/v6.0.0/website/docs/r/cloudfront_distribution.html.markdown), [OAC](https://raw.githubusercontent.com/hashicorp/terraform-provider-aws/v6.0.0/website/docs/r/cloudfront_origin_access_control.html.markdown), S3 bucket/public-access/ownership/policy and response-headers resources in the same official versioned docs.
- AWS [OAC bucket policy](https://docs.aws.amazon.com/AmazonCloudFront/latest/DeveloperGuide/private-content-restricting-access-to-s3.html), CLI [sync](https://docs.aws.amazon.com/cli/latest/reference/s3/sync.html), [invalidation](https://docs.aws.amazon.com/cli/latest/reference/cloudfront/create-invalidation.html).

## Verification

Issue #9 specifies manual frontend/infrastructure seams: local build/type check,
mobile/desktop browser smoke with stub SSE, then live URL smoke after deployment.
Live smoke: streaming, bilingual direction, sources, calculator status, new thread,
quota/error handling and private S3 access. No infrastructure apply in this change.

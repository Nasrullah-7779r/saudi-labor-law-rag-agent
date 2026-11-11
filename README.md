# Saudi Labor Law RAG Agent

Bilingual (AR/EN) serverless RAG agent over the Saudi Labor Law, with article citations. Not legal advice.

## API

Live tracer: API Gateway REST (stream transfer mode) → Lambda (container, Lambda Web Adapter `response_stream`) → FastAPI.

```
curl -N -X POST "$(terraform -chdir=infra/live output -raw api_url)/chat" \
  -H 'content-type: application/json' -d '{"message":"What is the notice period?"}'
```

`GET /health` returns `{"status":"ok"}`. Event contract: [docs/stream-protocol.md](docs/stream-protocol.md). Run locally: `cd backend && uv run uvicorn labor_law_agent.api:app --reload`.

The deploy workflow applies the ECR repo, pushes `backend:<sha>`, applies the rest, then rolls the image out with `update-function-code` (Terraform ignores `image_uri` after creation). No reserved concurrency yet (deferred from #3): this account's Lambda concurrency limit is 10, and Lambda only allows reserving up to unreserved concurrency minus 100, so nothing can be reserved. Until then the caps are the stage throttle (2 req/s, burst 5) and the account limit of 10. After a Service Quotas increase (Lambda → "Concurrent executions") above 100, add `reserved_concurrent_executions = 5` to `aws_lambda_function.chat`.

## Infrastructure

```
PR ──► CI: backend (ruff, mypy, pytest) + terraform plan ──OIDC──► saudi-labor-law-rag-agent-github-plan (read-only)
main ──► Deploy: terraform apply ─────────────────────────OIDC──► saudi-labor-law-rag-agent-github-deploy
                                    state: s3://<bucket>/live/terraform.tfstate (+ .tflock, native S3 locking)
```

- `infra/bootstrap/` — split by concern (`state_bucket.tf`, `github_oidc.tf`, `iam_github_*_role.tf`); one-time, applied by a human with local state: state bucket, GitHub OIDC provider, plan/deploy roles.
- `infra/live/` — everything else; planned on PRs, applied on merge to `main`.

No AWS access keys are stored in GitHub. CI authenticates via GitHub OIDC; the deploy role trusts only `refs/heads/main`, the plan role only `pull_request` events from this repo.

### Bootstrap (once)

Requires Terraform >= 1.11 (native S3 locking) and admin AWS credentials on your machine.

```bash
cd infra/bootstrap
terraform init
terraform apply -var="state_bucket_name=<globally-unique-name>"
terraform output
```

If the account already has a GitHub OIDC provider (AWS allows one per URL), import it before `apply`, and run `terraform state rm aws_iam_openid_connect_provider.github_actions` before any `destroy` so other projects keep it:

```bash
terraform import -var="state_bucket_name=<name>" aws_iam_openid_connect_provider.github_actions arn:aws:iam::<account-id>:oidc-provider/token.actions.githubusercontent.com
```

Keep the resulting `terraform.tfstate` safe (it is git-ignored). The trust policies match GitHub's OIDC `sub` exactly. This repo uses the immutable format (`repo:OWNER@ID/REPO@ID:...`); if `AssumeRoleWithWebIdentity` is denied, compare `github_oidc_sub_prefix` with `gh api repos/<owner>/<repo>/actions/oidc/customization/sub --jq .sub_claim_prefix`.

Region is fixed to `us-east-1` in code (`variables.tf`, live backend block, workflow `env`). Then set these GitHub **repository variables** (Settings → Secrets and variables → Actions → Variables — not secrets, none are credentials):

| Variable | Value |
| --- | --- |
| `TF_STATE_BUCKET` | `state_bucket_name` output |
| `AWS_PLAN_ROLE_ARN` | `github_plan_role_arn` output |
| `AWS_DEPLOY_ROLE_ARN` | `github_deploy_role_arn` output |
| `AWS_INGEST_ROLE_ARN` | `github_ingest_role_arn` output |
| `PINECONE_INDEX_NAME` | e.g. `saudi-labor-law` (created on first ingest) |

## Law ingest

Source: the Arabic consolidated Labor Law on the Bureau of Experts (BOE) site,
<https://laws.boe.gov.sa/BoeLaws/Laws/LawDetails/08381293-6388-48e2-8ad2-a9a700f2aa94/1>.
The text is fetched at run time; it is not committed (tests use a short excerpt fixture).

```
BOE HTML ─► parse_articles ─► chunk_article (≤1500 chars) ─► Bedrock cohere.embed-multilingual-v3 ─► Pinecone upsert
              │ aborts on gaps/duplicates            ids art-<NNN>-<NN>, stale ids deleted
```

1. After `live` applies, set the key once: `aws secretsmanager put-secret-value --secret-id saudi-labor-law-rag-agent/pinecone-api-key --secret-string '<key>'`.
2. Run **Actions → Ingest** with the version date of the latest amendment in force. The serverless index (1024-d, cosine, `us-east-1`) is created on first run. Re-runs are idempotent.

Known gaps (v1):
- Articles 229–242 (penalties part) are skipped: the BOE page mixes pre-2013 numbering with renumbered and added articles (duplicate 233–235, "229 bis", unheaded "currently X / formerly Y" items).
- The BOE page only shows the first chapter heading, so `chapter` is mostly empty; `part` is set on every article.

Local plan against remote state:

```bash
cd infra/live
terraform init -backend-config="bucket=<bucket>"
terraform plan
```

Known trade-offs (revisit once the live stack has real resources):
- The deploy role has `AdministratorAccess`; scope it down. Protect `main` (required reviews + required `CI` checks), since any workflow on `main` can assume it.
- Any same-repo PR can assume the read-only plan role. Fork PRs get no OIDC token, so their plan job fails.

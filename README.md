# Saudi Labor Law RAG Agent

Bilingual (AR/EN) serverless RAG agent over the Saudi Labor Law, with article citations. Not legal advice.

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
terraform apply -var="state_bucket_name=<globally-unique-name>" -var="aws_region=<region>"
terraform output
```

Keep the resulting `terraform.tfstate` safe (it is git-ignored). Then set these GitHub **repository variables** (Settings → Secrets and variables → Actions → Variables — not secrets, none are credentials):

| Variable | Value |
| --- | --- |
| `AWS_REGION` | same `aws_region` used at bootstrap (bucket region) |
| `TF_STATE_BUCKET` | `state_bucket_name` output |
| `AWS_PLAN_ROLE_ARN` | `github_plan_role_arn` output |
| `AWS_DEPLOY_ROLE_ARN` | `github_deploy_role_arn` output |

Local plan against remote state:

```bash
cd infra/live
terraform init -backend-config="bucket=<bucket>" -backend-config="region=<region>"
terraform plan
```

Known trade-offs (revisit once the live stack has real resources):
- The deploy role has `AdministratorAccess`; scope it down. Protect `main` (required reviews + required `CI` checks), since any workflow on `main` can assume it.
- Any same-repo PR can assume the read-only plan role. Fork PRs get no OIDC token, so their plan job fails.
- Bootstrap fails with `EntityAlreadyExists` if the account already has a GitHub OIDC provider; import it first.

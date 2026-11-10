# Saudi Labor Law RAG Agent

## Agent skills

### Issue tracker

Issues and specs live in this repo's GitHub Issues, via the `gh` CLI. See `docs/agents/issue-tracker.md`.

### Triage labels

Default vocabulary: `needs-triage`, `needs-info`, `ready-for-agent`, `ready-for-human`, `wontfix`. See `docs/agents/triage-labels.md`.

### Domain docs

Single-context: `GLOSSARY.md` + `docs/adr/` at the repo root. See `docs/agents/domain.md`.

## General guidelines
- Verify before acting. Never assume; validate facts, requirements and context first.
- Understand the existing architecture before changing it.
- Respect Terraform boundaries (permissions, infrastructure) when adding features.
- Every new Lambda in the infra must also be added to the CI/CD pipeline so it gets updated.

## Plans
- Descriptive filenames (e.g. `usage-guard-plan.md`), never generic or random.
- Every plan includes an architecture diagram (e.g. ASCII flow of components/requests), not just prose steps.
- Keep plans simple and to the point, following industry standards. Check current online docs while planning so the plan is right the first time.

## Documentation-grounded code (mandatory)
Do not write code against an external library, SDK, framework or cloud API without first consulting Context7 or the vendor's official docs. Training memory is not a source.
- Look it up first: Context7 MCP (`resolve-library-id` → `query-docs`), the vendor's docs MCP/skill (AWS, Pinecone, …), or the official docs page.
- Verify exact method/parameter names, required vs optional fields, return shapes, auth, version/deprecation status and error semantics.
- Never invent an API surface. If the docs don't show it, it doesn't exist; say so.
- Match the version pinned in the project (`pyproject.toml`/`uv.lock`, `package.json`, Terraform provider constraints), and note when docs differ across versions.
- If docs are ambiguous or contradict existing code, stop and report the conflict.
- Cite the library/version and doc section or URL in the plan, the PR description, or a short code comment where behaviour is non-obvious.
- Applies to planning too: any API call in a plan must be verified in the docs first.

## Mirroring existing patterns
When told to "mirror"/"follow the same pattern as" existing code, judge the precedent first:
- Is it the pattern this codebase wants repeated, or one-off code that happens to be nearby?
- Is there a cleaner precedent elsewhere, or a shared helper that should be extracted?
- Would copying create another near-duplicate that belongs in one shared helper?
- Prefer an existing typed model over copying an untyped shape.

State which precedent you're extending and why. Don't propagate technical debt.

## IAM policy statements
Don't create a new statement when an existing one already has the same `Effect` and `Action`; add the ARN(s) to its `Resource` array. Only open a new block when `Effect` or `Action` differs. Keep a short comment saying what each ARN is for.

## Coupling and separation of concerns
- Each module, service or function owns one clearly defined responsibility.
- Don't mix layers: no business logic in route handlers, no data access in service logic.
- Place a new feature in the boundary it belongs to; don't reach across boundaries directly.
- Use explicit interfaces (function calls, events, defined contracts), not implicit dependencies or shared mutable state.
- Code that changes for different reasons lives in different places.

## Naming
Name identifiers after what they specifically are/do, not their generic category (e.g. `pinecone_api_key`, not `api_key`). Don't generalize for hypothetical future cases. Applies to DB attributes, functions, dependencies, routes, config keys and UI labels.

## Type safety
- Use the defined model (Pydantic model, TS interface, dataclass) instead of raw `dict`/`any`, especially in signatures and across boundaries.
- Parse external data (DB items, API payloads, events) into its typed model as early as possible, then pass the typed value on.
- Follow the codebase's parsing pattern (e.g. `Model(**item)`); parse defensively where the surrounding code tolerates bad data.
- If a needed shape isn't modelled yet, add the type rather than passing a raw dict.
- Build persisted items (e.g. DynamoDB `put_item` payloads) from a typed model with a serialisation method (`Model.dynamodb_item()`), not an inline dict at the call site.
- If the canonical model lives elsewhere and can't be imported, add a local typed mirror with a comment that it must stay in sync.

## Grilling
Ask one question at a time.

## Git workflow

### Worktrees for separate work
Do each ticket, fix, feature or chore branch in its own git worktree. Never switch branches or create branches in the main checkout.
- Exception: small changes (a few lines in one or two files, no design decisions) go in the main checkout: `git fetch origin && git switch -c <type>/<slug> origin/<base-branch>`, commit, push, then `git switch -` back. Only do this if there are no uncommitted changes to tracked files; otherwise use a worktree.
- Create worktrees beside the repo: `git fetch origin && git worktree add -b <type>/<slug> ../saudi-labor-law-rag-agent-<slug> origin/<base-branch>`. Verify the real base branch first; don't assume `main`.
- Do all edits, commits and pushes inside the worktree; show `git worktree list` after creating it.
- After merge: `git worktree remove <path>`, `git worktree prune`, then branch cleanup.

### Branch cleanup after merge
Once a PR is confirmed merged, delete its branch locally (`git branch -d`) and on origin (`git push origin --delete <branch>`). Never delete an unmerged branch. For squash/rebase merges, confirm with `gh pr view --json mergedAt`; only then is `git branch -D` acceptable. Remove any worktree on the branch first.

### Ticket status ships with the PR
If a ticket is tracked as a file in the repo, set it to done on the fix branch before opening or updating the PR, not as a follow-up commit.

## Testing

### Delegation
All test work goes to a subagent:
- **`test-writer`** (Sonnet): writes new tests.
- **`tester`** (cheapest model): edits existing tests, runs pytest/Vitest/lint/type checks/integration tests, investigates failures, regression checks, final validation.

The main agent does implementation and architecture, then hands verification to `tester`. It runs tests itself only when `tester` isn't available.

### Scope

Verify locally with targeted tests only: test files covering the changed modules (grep `backend/tests/` for the module/class names) plus new or updated tests. Don't run the full suite unless asked; CI covers it. If a targeted test fails, re-run it on the unmodified base and report pre-existing failures separately.

Backend (from `backend/`, targeted to changed files): `uv run pytest <test files>`, `uv run ruff check <files>`, `uv run mypy <src files>`. Repo-wide `ruff check .` / `mypy src` only when asked; CI runs them.

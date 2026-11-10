# Saudi Labor Law RAG Agent

## Agent skills

### Issue tracker

Issues and specs live in this repo's GitHub Issues, via the `gh` CLI. See `docs/agents/issue-tracker.md`.

### Triage labels

Default vocabulary: `needs-triage`, `needs-info`, `ready-for-agent`, `ready-for-human`, `wontfix`. See `docs/agents/triage-labels.md`.

### Domain docs

Single-context: `GLOSSARY.md` + `docs/adr/` at the repo root. See `docs/agents/domain.md`.

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

Verify locally with targeted tests only: test files covering the changed modules (grep `backend/tests/` for the module/class names) plus new or updated tests. Don't run the full suite unless asked; CI covers it. If a targeted test fails, re-run it on the unmodified base and report pre-existing failures separately.

Backend: `cd backend && uv run pytest <paths>`, `uv run ruff check .`, `uv run mypy src`.

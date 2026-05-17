# Locked Requirements

Locked requirements must not be removed, weakened, or silently changed.

## R-CORE-001: Preserve existing working behavior

Status: LOCKED

Do not remove working features unless explicitly requested.

## R-CORE-002: No unrelated rewrites

Status: LOCKED

Do not rewrite unrelated modules while implementing a focused task.

## R-CORE-003: Changes must be verifiable

Status: LOCKED

Every meaningful code change should have a validation path:

- tests
- lint
- typecheck
- manual verification
- documented reason why validation is unavailable

## R-CORE-004: Protect user secrets

Status: LOCKED

Do not read, print, commit, or push secrets.

Protected examples:

- `.env`
- `.env.*`
- API keys
- database credentials
- SSH keys
- cloud credentials
- personal tokens

## R-CORE-005: Preserve project memory files

Status: LOCKED

Do not delete the agent workflow files unless explicitly requested:

- `CLAUDE.md`
- `AGENTS.md`
- `docs/agent/*`

## R-DUAL-001: Codex owns planning and review

Status: LOCKED

Codex should produce:

- `08_IMPLEMENTATION_BRIEF.md`
- `10_REVIEW_REPORT.md`

Codex should not do large implementation work unless explicitly requested.

## R-DUAL-002: Claude Code owns implementation

Status: LOCKED

Claude Code should implement from:

- `08_IMPLEMENTATION_BRIEF.md`

Claude Code should not invent architecture beyond the brief unless it first writes a question or blocker.

## R-DUAL-003: Agent state is the source of truth

Status: LOCKED

If chat history and docs disagree, prefer:

1. `11_AGENT_STATE.md`
2. `04_TASK_HANDOFF.md`
3. `08_IMPLEMENTATION_BRIEF.md`
4. `09_CODING_HANDOFF.md`
5. `10_REVIEW_REPORT.md`
6. `git status` / `git log`

## R-GIT-001: Codex owns final git commit and push

Status: LOCKED

By default, final commit and push should be performed by Codex after review passes.

Default policy:

- Claude Code may implement code.
- Codex reviews and proposes final commit message.
- User approves finalization.
- Codex commits and pushes.

If the user wants full automation, they may add standing approval to `11_AGENT_STATE.md`.

## R-GIT-002: No push before review passes

Status: LOCKED

Do not push code until:

- implementation is complete,
- required tests/checks have run or unavailable checks are documented,
- `10_REVIEW_REPORT.md` has no Required Fixes,
- user approval or standing approval exists.

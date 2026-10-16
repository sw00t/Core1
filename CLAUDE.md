# Core1: instructions for Claude Code

Core1 is being refactored in place into v2, a reusable enterprise-realistic base for interview take-home
assignments. The full design is in `DESIGN.md`. Read it before doing anything.

## Working rules

- Do not make assumptions. When uncertain, stop and ask S.
- Work only on the `v2` branch. Never rewrite or delete the `v1-frozen` tag.
- Core1-agent and the `cascadia-activation-config` repo are out of scope. Do not read, modify, or depend on them.
- Follow the phases in `DESIGN.md` section 13 in order. Do not start a phase until S approves the previous one.
- Start each phase in plan mode and get S's approval of the plan before editing files.
- Ask before anything destructive or outward-facing: deleting clusters or volumes, force-pushing, creating or deleting
  GitHub repos, changing repo settings, opening PRs, changing Docker Desktop settings.
- Verify every third-party component (maintenance status, licence, arm64 image) before pinning it in `versions.env`.
  Record the result in `docs/decisions.md`.
- Desired state changes go through PRs to the GitOps repo. No direct `kubectl apply` to stage or prod outside
  bootstrap and the scenario engine's labelled fault injection.
- Never commit secrets. Tokens live in OpenBao or a git-ignored `.env`.

## Writing style for all files and messages

- No em dashes anywhere.
- Presentation slide titles: Title Case, no ending punctuation.
- Plain, spartan documentation. Short sentences.

## Stack

- macOS (M3 Pro, 36 GB), Docker Desktop, k3d (pinned in `.bin`), three clusters: mgmt, stage, prod.
- Python for services (FastAPI), mocks, CLI (Typer), traffic generator, scenario engine.
- GitHub for all git, PRs, and CI.

## Progress tracking

- Update `docs/progress.md` at the end of each work session: what was done, what is next, open questions.
- Keep `docs/backlog.md` for anything outside the current phase.

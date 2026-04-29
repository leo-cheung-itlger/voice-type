# ADR-0001: Establish lightweight project governance

## Status

Accepted

## Context

VoiceType was migrated to a new development directory and needed a stable entrypoint for humans and AI agents. The project also contains generated/runtime-heavy directories such as `venv/`, `frontend/node_modules/`, `logs/`, model files, and recordings that should not be committed.

## Decision

Use lightweight governance docs:

- `AGENTS.md` for AI entry rules and document authority
- `PROJECT_STATUS.md` for current state and next action
- `RUNBOOK.md` for setup, commands, validation, and failure notes
- `CHANGELOG.md` for meaningful changes and validation records
- `docs/adr/` for decisions that affect architecture or workflow

Keep `PROJECT_SUMMARY.md` as historical handoff context rather than daily execution truth.

## Consequences

- New agents can start from a low-context entrypoint.
- Operational commands and validation results have a single home.
- Git history can stay focused on source and project documents rather than local generated assets.

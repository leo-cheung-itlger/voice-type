# AGENTS

## First Read

Start with `PROJECT_STATUS.md`.

Read additional documents only when the task requires them:

- `PROJECT_SUMMARY.md`: imported handoff history from the previous AI session
- `RUNBOOK.md`: commands, validation, environment, and operations
- `CHANGELOG.md`: recent meaningful changes and validation notes
- `docs/adr/`: architecture and workflow decisions
- `README.md`: project overview, if added later

## Authority Order

1. Current user instructions
2. `PROJECT_STATUS.md`
3. `RUNBOOK.md` for operational and validation questions
4. `docs/adr/` for accepted decisions
5. `PROJECT_SUMMARY.md` as historical handoff context
6. Source code and config for implementation truth

## Working Rules

- Keep changes scoped to the current task.
- Do not revert unrelated user changes.
- Update `PROJECT_STATUS.md` and `CHANGELOG.md` after meaningful code, config, data, or operational changes.
- Update `RUNBOOK.md` when commands, setup, validation, or failure handling changes.
- Record major architecture, persistence, provider, or workflow decisions in `docs/adr/`.
- Do not commit virtual environments, installed dependencies, logs, model files, recordings, or secrets.

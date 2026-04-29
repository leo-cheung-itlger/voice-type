# PROJECT_STATUS

## Current Status

- Status: governance initialized after project directory migration.
- Active goal: stabilize VoiceType as a maintainable fork/rework of CapsWriter-Offline with Python ASR services, client output control, API, and Vue frontend.
- Current blocker: full frontend production build has not been validated in the sandbox because Vite/esbuild process spawn was denied.

## Current Architecture

- Python ASR server: `server/asr_server.py`, `server/asr_engine.py`
- Python input/output client: `client/client_core.py`, `client/output.py`, `client/recorder.py`
- API/control backend: `api/api_server.py`
- Shared modules: `common/`, `config/`
- Frontend: `frontend/` using Vue 3, TypeScript, Vite, Pinia, and Vue Router
- Historical handoff: `PROJECT_SUMMARY.md`

## Validation Baseline

- Python syntax compile: passed on 2026-04-29.
- Frontend typecheck: passed on 2026-04-29 with `node node_modules\vue-tsc\index.js --noEmit`.
- Frontend build: blocked on 2026-04-29 by sandbox `esbuild spawn EPERM`; rerun outside the sandbox or in a normal terminal.

## Next Minimal Action

- Run the frontend production build outside the sandbox: `cd frontend && npm run build`.
- After build passes, make the first Git commit containing source files and governance docs.

## Last Updated

- 2026-04-29

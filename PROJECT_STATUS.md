# PROJECT_STATUS

## Current Status

- Status: Phase 1/2 implementation in progress; Web control console is now a compact desktop-window-style app with persisted config and operational APIs.
- Active goal: stabilize VoiceType daily voice input before wrapping the same frontend in Tauri.
- Current blocker: no active runtime blocker for the Web + Python daily ASR loop; manual right-Shift dictation still needs user-side microphone/output confirmation.
- Governance note: every substantial task now requires an explicit validation gate and browser/runtime checks for UI work.

## Current Architecture

- Python ASR server: `server/asr_server.py`, `server/asr_engine.py`
- Python input/output client: `client/client_core.py`, `client/output.py`, `client/recorder.py`
- API/control backend: `api/api_server.py`
- Shared modules: `common/`, `config/`
- Frontend: `frontend/` using Vue 3, TypeScript, Vite, Pinia, and Vue Router; designed as a compact 420-520px desktop control window
- Historical handoff: `PROJECT_SUMMARY.md`

## Validation Baseline

- Python syntax compile: passed on 2026-04-29.
- Frontend production build: passed on 2026-04-29 with `cmd /c npm run build`.
- API smoke: passed on 2026-04-29 for `/api/status`, `/api/health`, `/api/config`, `/api/models`, and `/api/hotwords/hot-zh.txt`.
- Browser smoke: compact control console loads at `http://127.0.0.1:52343/#/`; latest browser pass had no console errors.
- Client smoke: UI-started client stays running after startup and no longer crashes on the `websockets` `.closed` compatibility issue.
- Recording feedback smoke: client-side beep/topmost desktop notification module runs without errors; Settings page exposes notification and sound toggles.
- Model smoke: selected `qwen3-asr-1.7b` resolves to the existing local CapsWriter model directory at `C:\Program Files\CapsWriter-Offline-Windows-64bit\models\Qwen3-ASR-1.7B`.
- Fixture ASR smoke: direct model recognition passed 3/3 mp3 samples; WebSocket service recognition through the current managed ASR server passed 3/3 samples on 2026-04-29.
- Runtime smoke: current API reports `server.managed=true` and `client.managed=true`; browser dashboard shows Ready, latest result, and history entries from the fixture run.

## Next Minimal Action

- Run final manual daily ASR smoke: press right Shift, verify topmost prompt/beep, speak a short phrase, release, and confirm target output plus saved recording.
- After smoke passes, commit the Phase 1/2 implementation.

## Last Updated

- 2026-04-29

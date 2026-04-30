# PROJECT_STATUS

## Current Status

- Status: Phase 1/2 implementation in progress; Web control console is now a compact desktop-window-style app with persisted config, operational APIs, a working first file-transcription workspace, and VoiceType-specific ports.
- Active goal: stabilize VoiceType daily voice input, then expand the same frontend into Tauri with file transcription and subtitle export.
- Current blocker: manual right-Shift dictation still needs user-side microphone/output confirmation. VoiceType now uses `55341/55342/55343`, so old CapsWriter on `52341` should no longer block this project.
- Governance note: every substantial task now requires an explicit validation gate and browser/runtime checks for UI work.

## Current Architecture

- Python ASR server: `server/asr_server.py`, `server/asr_engine.py`
- Python input/output client: `client/client_core.py`, `client/output.py`, `client/recorder.py`
- API/control backend: `api/api_server.py`
- Shared modules: `common/`, `config/`
- Frontend: `frontend/` using Vue 3, TypeScript, Vite, Pinia, and Vue Router; designed as a compact 420-520px desktop control window
- File transcription queue: `common/transcription.py` plus `/api/transcriptions*`, `/api/ffmpeg/status`, and `/api/llm/config`
- Runtime ports: ASR `55341`, API `55342`, frontend `55343`
- Agent integration guide: `.agents/skills/voicetype-transcription/SKILL.md`
- Historical handoff: `PROJECT_SUMMARY.md`

## Validation Baseline

- Python syntax compile: passed on 2026-04-30.
- Frontend production build: passed on 2026-04-30 with `cmd /c npm run build`.
- API smoke: passed on 2026-04-30 for `/api/status`, `/api/health`, `/api/config`, `/api/models`, `/api/hardware`, and `/api/ffmpeg/status`.
- Browser smoke: compact control console loads at `http://127.0.0.1:55343/#/`; latest browser pass had no console errors.
- Client smoke: UI-started client stays running after startup and no longer crashes on the `websockets` `.closed` compatibility issue.
- Recording feedback smoke: client-side beep/topmost desktop notification module runs without errors; Settings page exposes notification and sound toggles.
- Model smoke: selected `qwen3-asr-1.7b` resolves to the existing local CapsWriter model directory at `C:\Program Files\CapsWriter-Offline-Windows-64bit\models\Qwen3-ASR-1.7B`.
- Fixture ASR smoke: direct model recognition passed 3/3 mp3 samples; WebSocket service recognition through the current managed ASR server passed 3/3 samples on 2026-04-29.
- Runtime smoke: `stop.bat` releases `55341/55342/55343`; `start.bat` starts API/frontend/ASR/client; current API reports `server.managed=true`, `client.managed=true`, and no process conflicts.
- File transcription API smoke: local ffmpeg is available at `tools/ffmpeg/bin/ffmpeg.exe`; mp3 and generated mp4 transcription tasks completed and produced JSON/TXT/SRT outputs on 2026-04-29.
- Browser transcription page smoke: `http://127.0.0.1:55343/#/transcriptions` loads, no longer shows ffmpeg missing, and has no new console errors.
- Qwen route note: `Qwen3-ASR-1.7B` is installed and remains the high-quality model; benchmark on the fixed mp3 sample measured about 17.87s model load plus 20.65s inference on CPU PyTorch. `Qwen3-ASR-0.6B` is listed as the low-latency candidate but is not installed locally yet. Current PyTorch is CPU-only, so CUDA acceleration is not active.

## Next Minimal Action

- Run final manual daily ASR smoke: press right Shift, verify topmost prompt/beep, speak a short phrase, release, and confirm target output plus saved recording.
- Next engineering target: validate right-Shift daily input on the clean `55341` stack, then install/benchmark `Qwen3-ASR-0.6B` and decide whether to pursue CUDA PyTorch or GGUF/Vulkan before packaging the compact UI in Tauri.

## Last Updated

- 2026-04-30

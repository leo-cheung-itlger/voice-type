# PROJECT_STATUS

## Current Status

- Status: Phase 1/2 implementation in progress; Web control console is now a compact desktop-window-style app with persisted config, operational APIs, a working first file-transcription workspace, VoiceType-specific ports, a verified CUDA route for the installed Qwen model, a compiled Tauri desktop shell, and improved daily hotkey/archiving/model-management UX.
- Active goal: stabilize VoiceType daily voice input, then expand the same frontend into Tauri with file transcription and subtitle export.
- Current blocker: manual right-Shift dictation still needs user-side microphone/output confirmation. VoiceType now uses `55341/55342/55343`, so old CapsWriter on `52341` should no longer block this project. Qwen CUDA is working but still not sub-second; the fastest measured local model is Paraformer CPU, which is intentionally blocked by `gpu_required=true`. The standard release EXE path may remain locked if an old `voicetype.exe` process is held by Everything; a verified temporary build output exists under `frontend/src-tauri/target-codex-build/`.
- Governance note: every substantial task now requires an explicit validation gate and browser/runtime checks for UI work.

## Current Architecture

- Python ASR server: `server/asr_server.py`, `server/asr_engine.py`
- Python input/output client: `client/client_core.py`, `client/output.py`, `client/recorder.py`
- API/control backend: `api/api_server.py`
- Shared modules: `common/`, `config/`
- Frontend: `frontend/` using Vue 3, TypeScript, Vite, Pinia, and Vue Router; designed as a compact 420-520px desktop control window
- File transcription queue: `common/transcription.py` plus `/api/transcriptions*`, `/api/ffmpeg/status`, and `/api/llm/config`
- Runtime ports: ASR `55341`, API `55342`, frontend `55343`
- Desktop shell: `frontend/src-tauri/` uses Tauri v2, with a 480x720 window, tray Show/Quit menu, close-to-tray behavior, and runtime startup through `scripts/start-runtime.ps1`
- Daily recording archive: valid hotkey recordings now use `data/archive/YYYY/MM/DD/HHMMSS_<task_id>/recording.wav` plus `result.json`; short presses below `client.min_press_seconds` are ignored before ASR submission.
- Agent integration guide: `.agents/skills/voicetype-transcription/SKILL.md`
- Historical handoff: `PROJECT_SUMMARY.md`

## Validation Baseline

- Python syntax compile: passed on 2026-05-01.
- Frontend production build: passed on 2026-05-01 with `npm run build`.
- API smoke: passed on 2026-05-01 for `/api/status`, `/api/health`, `/api/config`, and `/api/models`; `/api/models` includes download links and `/api/models/{id}/open-folder` opened the expected model root.
- Browser smoke: compact Settings page loads at `http://127.0.0.1:55343/#/settings`; 2026-05-01 viewport smoke showed shortcut capture, short-press threshold, archive path, and model controls.
- Client smoke: UI-started client stays running after startup and no longer crashes on the `websockets` `.closed` compatibility issue.
- Recording feedback smoke: client-side beep/topmost desktop notification module runs without errors; Settings page exposes notification and sound toggles.
- Model smoke: selected `qwen3-asr-1.7b` resolves to the existing local CapsWriter model directory at `C:\Program Files\CapsWriter-Offline-Windows-64bit\models\Qwen3-ASR-1.7B` and loads onto `NVIDIA GeForce RTX 5070 Ti Laptop GPU` through PyTorch CUDA.
- Fixture ASR smoke: direct model recognition passed 3/3 mp3 samples; WebSocket service recognition through the current managed ASR server passed 3/3 samples on 2026-04-29.
- Runtime smoke: `stop.bat` releases `55341/55342/55343`; `start.bat` starts API/frontend/ASR/client; current API reports `server.managed=true`, `client.managed=true`, and no process conflicts.
- File transcription API smoke: local ffmpeg is available at `tools/ffmpeg/bin/ffmpeg.exe`; mp3 and generated mp4 transcription tasks completed and produced JSON/TXT/SRT outputs on 2026-04-29.
- Browser transcription page smoke: `http://127.0.0.1:55343/#/transcriptions` loads, no longer shows ffmpeg missing, and has no new console errors.
- Qwen route note: `Qwen3-ASR-1.7B` is installed and remains the high-quality GPU model. Latest fixed mp3 benchmark measured `qwen3-asr-1.7b::pytorch-cuda` at about 31.79s cold load plus 4.61s inference, versus `qwen3-asr-1.7b::pytorch-cpu` at about 15.56s load plus 17.76s inference. `Qwen3-ASR-0.6B` and `Qwen3-ASR-1.7B-GGUF` are listed as low-latency/GPU candidates but are not installed locally yet.
- Benchmark harness: `scripts/model_benchmark.py` and `/api/models/benchmark-all` write per-model/mode records to ignored runtime data at `data/model_benchmark.json`, including missing-model records without fake inference timings. Paraformer CPU now initializes correctly through `OfflineRecognizer.from_paraformer` and measured about 0.16s inference, but sherpa-onnx CUDA is unavailable in the current Python environment and is blocked under `gpu_required=true`.
- Desktop shell smoke: MSVC Build Tools are installed and available through `VsDevCmd.bat`; Tauri release build passed on 2026-05-01 using temporary `CARGO_TARGET_DIR=frontend/src-tauri/target-codex-build` because an old release `voicetype.exe` was locked. The temporary build produced `target-codex-build/release/voicetype.exe`, MSI, and NSIS installer; the EXE starts without `55343` and API health stays JSON on `55342`.

## Next Minimal Action

- Run final manual daily ASR smoke: press right Shift longer than `0.1s`, verify topmost prompt/beep, speak a short phrase, release, and confirm target output plus `data/archive/.../recording.wav` and `result.json`.
- Close or release the old locked `voicetype.exe` process before rebuilding the normal `frontend/src-tauri/target/release/voicetype.exe`; until then use the verified temporary EXE under `target-codex-build/release/`.

## Last Updated

- 2026-05-01

# CHANGELOG

## 2026-04-30

- Added initial Tauri v2 desktop-shell scaffolding under `frontend/src-tauri/`, including a 480x720 main window, tray Show/Quit menu, close-to-tray behavior, and runtime start/stop hooks.
- Added `scripts/start-runtime.ps1` so a desktop shell can start or reuse the Python API, ASR server, and recording client without launching a browser frontend.
- Updated frontend API base resolution so bundled Tauri pages can call `http://127.0.0.1:55342/api` instead of a broken relative `/api` path.
- Recorded the staged packaging strategy in ADR-0004: Tauri dev shell first, portable Windows alpha second, formal installer only after runtime and model behavior are stable.
- Validation: frontend typecheck passed; frontend production build passed; `scripts/start-runtime.ps1` reported runtime ready with API/ASR/client already running. Tauri compile/package is pending dependency installation approval for `@tauri-apps/*` npm packages and Rust crates.

- Installed CUDA-enabled PyTorch in the project `venv` and changed Qwen initialization so the internal Transformers model is moved to CUDA when `gpu_required=true`.
- Added hard blocking for fake GPU paths: Qwen no longer silently falls back to CPU when GPU is required, and sherpa-onnx CUDA now fails clearly when the current environment lacks a CUDA execution provider.
- Fixed Paraformer initialization for sherpa-onnx 1.13 by using `OfflineRecognizer.from_paraformer`, so Paraformer CPU benchmarks now run.
- Updated benchmark selection and Settings UI so the main model row prefers successful GPU results when GPU is required, instead of showing a slower CPU result or contradictory "failed/OK" text.
- Validation: PyTorch reports `2.11.0+cu128`, CUDA `12.8`, and `NVIDIA GeForce RTX 5070 Ti Laptop GPU`; direct Qwen CUDA initialization succeeds; fixed sample benchmark measured `qwen3-asr-1.7b::pytorch-cuda` at about 31.79s load plus 4.61s inference and `qwen3-asr-1.7b::pytorch-cpu` at about 15.56s load plus 17.76s inference; Paraformer CPU measured about 1.31s load plus 0.16s inference; Paraformer CUDA correctly records an init failure because sherpa-onnx CUDA is unavailable. Python compile, frontend typecheck/build, API status/config/hardware/recommendation, ffmpeg status, WebSocket service fixture smoke, and browser Settings page smoke passed.

- Added the repeatable model benchmark harness via `scripts/model_benchmark.py` and `/api/models/benchmark-all`, with per-model/mode records persisted to `data/model_benchmark.json` for model, backend, acceleration, actual GPU use, load/inference/total seconds, text, ok, and error.
- Validation: Python compile passed for `api/api_server.py` and `scripts/model_benchmark.py`; `scripts/model_benchmark.py --list-models` listed the configured model ids; full benchmark harness wrote real records for all configured model/mode plans. `qwen3-asr-1.7b::pytorch-cpu` passed with about 19.31s load and 21.11s inference; missing models were recorded as missing; Qwen CUDA and paraformer sherpa-onnx modes recorded init failures instead of fake timings.
- Moved VoiceType runtime ports to `55341/55342/55343` to avoid CapsWriter `52341` collisions, with legacy saved `52341/52342` config values migrated at load time.
- Reworked `start.bat` / `stop.bat` and the PowerShell helpers so they clean project-owned duplicate processes, use the project `venv`, and start/stop API, frontend, ASR server, and recording client together.
- Added API process conflict detection for managed server/client status, hardware/CUDA reporting, and Qwen model benchmark endpoints.
- Added Settings UI hardware/model benchmark display and updated the client notification flow to show recording, analyzing with elapsed time, queued recordings, success, and failure states.
- Validation: Python compile passed; frontend typecheck and production build passed; `stop.bat` released `55341/55342/55343`; `start.bat` started API/frontend/ASR/client; `/api/status` reports managed server/client with no conflict; `/api/hardware` detects RTX 5070 Ti with CPU-only PyTorch; `/api/ffmpeg/status` remains available; model benchmark reports missing `Qwen3-ASR-0.6B` and `Qwen3-ASR-1.7B` at about 17.87s load plus 20.65s inference on the fixed mp3 sample; service fixture smoke passed through `55341`; browser Settings page at `55343` has no console errors.

## 2026-04-29

- Added project-local ffmpeg fallback detection at `tools/ffmpeg/bin`, with `tools/ffmpeg/` ignored by Git for local binary installs.
- Installed local ffmpeg 8.1 essentials for this workspace and verified `/api/ffmpeg/status` returns `available=true`.
- Validation: Python compile passed; frontend typecheck/build passed; mp3 and generated mp4 transcription task completed through the HTTP API; JSON/TXT/SRT outputs were created and inspected; browser Transcriptions page no longer shows ffmpeg missing and had no new console errors. Client was restarted through the API after dev-process restart.

## 2026-04-29

- Added the first file transcription module: HTTP queue APIs, ffmpeg detection, browser upload support, path-based tasks, JSON/TXT/SRT export, cancellation, and OpenAI-compatible LLM polishing config.
- Added the compact frontend Transcriptions page with drag/drop upload confirmation, path-based task creation, queue status, format selection, and LLM polishing controls.
- Added project-local agent Skill instructions at `.agents/skills/voicetype-transcription/SKILL.md` and ADR-0003 documenting the API-first transcription design.
- Validation: Python compile passed; frontend typecheck and production build passed; new API endpoints smoke-tested on an isolated API port; browser Transcriptions page loaded after restarting the API/frontend dev processes with no new console errors. Full mp3/mp4 transcription smoke is blocked because this machine currently has no `ffmpeg` on PATH or `VOICETYPE_FFMPEG_PATH`.

## 2026-04-29

- Fixed the audio sample-rate contract between client and ASR server: audio start/end messages now carry `sample_rate`, and the server no longer hardcodes raw audio as 16 kHz.
- Added `scripts/asr_fixture_smoke.py` to run repeatable mp3 fixture recognition in direct-model mode or WebSocket service mode.
- Added CPU fallback for Qwen3-ASR when CUDA is requested but unavailable.
- Filtered API health recent issues to the current API process so old failure logs do not appear as current dashboard errors.
- Validation: Python compile passed; frontend typecheck/build passed; direct fixture recognition passed 3/3; managed WebSocket ASR service fixture recognition passed 3/3; API health shows managed server/client and no recent issues; browser dashboard shows Ready and the fixture recognition history.

## 2026-04-29

- Added client-side recording feedback: pressing the configured shortcut now plays a short beep and shows a small topmost desktop notification; releasing it plays another beep and shows a sent notification.
- Added `notification_enabled` and `notification_sound` client config fields and Settings toggles.
- Validation: Python compile passed; frontend typecheck and production build passed; API was restarted and `/api/config` exposes the new fields; browser Settings page shows the new toggles; direct notifier smoke ran without errors.

## 2026-04-29

- Fixed the client WebSocket compatibility bug where `websockets` `ClientConnection` no longer exposes `.closed`, causing CapsLock recording startup to crash.
- Changed API-managed server/client launches to hidden background processes with stdout/stderr logs instead of visible console windows.
- Added hidden dev startup/stop helper scripts and updated `start.bat` / `stop.bat` so API/frontend dev processes do not remain in separate black console windows.
- Added model directory resolution for the installed CapsWriter model location and confirmed `qwen3-asr-1.7b` resolves to the local `Qwen3-ASR-1.7B` directory.
- Validation: Python compile passed; frontend typecheck and production build passed; API/frontend hidden start scripts were smoke-tested; browser console showed no frontend errors; UI-started client remained running without the previous `.closed` crash.

## 2026-04-29

- Added a validation-gate requirement to the project governance workflow: substantial tasks must define acceptance criteria, run validation, and report blockers explicitly.
- Expanded `RUNBOOK.md` with frontend, API, and daily ASR acceptance harness steps.
- Added ADR-0002 to record validation gates as part of the project workflow.
- Validation: documentation and governance files updated; no runtime tests required for this docs-only change.

## 2026-04-29

- Added persisted app configuration APIs, health/model/log/hotword endpoints, and model selection support.
- Added ASR monitor broadcasting so the Web console can receive recognition results through `/ws/recognition`.
- Fixed client recording save path to use configured `audio_dir` and pass `audio_path` into history.
- Reworked the Vue UI into a compact desktop-window-style control console with dashboard, history, hotword editor, stats, and settings tabs.
- Updated startup scripts so `start.bat` launches API and frontend while service processes are controlled from the console.
- Validation: Python syntax compile passed; frontend production build passed; API smoke passed for status, health, config, models, and hotword read endpoints; browser smoke loaded the compact console with only a favicon 404.

## 2026-04-29

- Re-initialized the migrated project directory as a Git repository.
- Added lightweight project governance files: `AGENTS.md`, `PROJECT_STATUS.md`, `RUNBOOK.md`, and `docs/adr/0001-project-governance.md`.
- Added `.gitignore` for local environments, installed dependencies, logs, model files, recordings, and secrets.
- Validation: Python syntax compile passed; frontend typecheck passed; frontend production build blocked by sandbox `esbuild spawn EPERM`.

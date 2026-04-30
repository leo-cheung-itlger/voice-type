# CHANGELOG

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

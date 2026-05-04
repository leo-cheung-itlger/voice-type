# CHANGELOG

## 2026-05-04

- Added `scripts/mic_format_probe.py`, an independent microphone-format diagnostic that records once from the selected input and writes raw 48k stereo PCM16, fixed channel-0/channel-1 48k mono, and scipy-resampled 16k mono WAV variants under ignored `data/mic_format_tests/`, then optionally runs Qwen3-ASR 1.7B on the ASR candidates.
- Validation: `py_compile scripts\mic_format_probe.py` passed; `--help` printed expected options; `--seconds 1 --no-asr` recorded from `3.5mm麦克风 (Senary Audio) / Windows WASAPI / 48000Hz / 2ch` and wrote all WAV/result files; full `--seconds 1` loaded Qwen3-ASR 1.7B onto CUDA and ran recognition on channel 0, channel 1, and 16k mono candidates. The validation sample was silence-level input, so ASR text was empty by design. ffprobe confirmed `raw_48k_stereo.wav` is `pcm_s16le / 48000Hz / 2ch / 16-bit` and `standard_asr_16k_mono.wav` is `pcm_s16le / 16000Hz / 1ch / 16-bit`.

- Added default-on post-capture automatic microphone gain. Shared capture now chooses the mono channel first, then applies PCM16 gain targeting about `0.08` RMS with a `20dB` max boost and `0.95` peak limit before saving `recording.wav` or sending audio to ASR. The capture metadata now records `source_audio_level`, `processed_audio_level`, `gain_db`, `input_output_gain_ratio`, `volume_policy`, and `auto_gain_enabled`.
- Wired `client.auto_gain_enabled=true` through config, API-managed client startup args, hot-reloaded client config, `/api/audio/test-input`, advanced microphone scanning, the validation harness, and the Settings UI. Settings now exposes an `自动增益` toggle and microphone test results show gain when applied.
- Validation: Python compile passed for API/server/client/shared audio/config/validation modules; frontend `vue-tsc --noEmit` and production build passed; synthetic PCM16 checks confirmed quiet audio is boosted, loud audio is not further boosted, and silence remains `too_quiet`; the user-provided quiet `recording.wav` was boosted by `17.668dB` to `rms_ratio=0.079999`/`peak_ratio=0.75943` and the running `qwen3-asr-1.7b` service still recognized the sentence; runtime restart returned managed ASR/client; Settings browser smoke showed the `自动增益` control with no console warnings/errors; `/api/audio/test-input` returned the new gain fields and correctly skipped gain for a silence-level sample. A user-side live Caps Lock recording remains the final normal-distance microphone playback check.

- Locked microphone mono output to pass-through volume. Stereo captures no longer use average downmix as the saved/ASR audio path, because that could attenuate the signal on 2ch devices. The capture pipeline now chooses a real input channel and records `volume_policy=passthrough_no_gain` plus `input_output_gain_ratio`, so the emitted mono PCM keeps the selected channel's original level instead of applying gain, suppression, or averaging.
- Validation: Python compile passed for API/client/recorder/shared audio modules; synthetic stereo validation confirmed an old remembered `average` preference now resolves to `channel_0` with peak preserved and `input_output_gain_ratio=1.0`; frontend typecheck/build passed; runtime restart returned managed ASR/client; `/api/audio/test-input` on the current 3.5mm WASAPI device reported `normalized_strategy=channel_0`, `volume_policy=passthrough_no_gain`, and `input_output_gain_ratio=1.0`. The API sample was quiet because no live speech was played during validation.

- Cleaned up Settings model rows and History archive controls. Missing models now show shorter status text without repeating `模型缺失`, GGUF candidates are labeled as CPU/GGUF quantized, and the model download action opens a chooser with one-click ModelScope download plus the official model webpage. History rows no longer print full recording/result paths; top-level and per-entry buttons open audio/result folders instead, and each row labels recognition time as `推理 x.xs`.
- Added safe history folder-open API endpoints constrained to VoiceType archive/data roots, added ModelScope IDs to `/api/models`, and added controlled `/api/models/{model_id}/download-modelscope` jobs. The job installs `modelscope` into the project venv if missing, then downloads via `snapshot_download(..., local_dir=<model install dir>)` and writes a log under `logs/`.
- Validation: `py_compile api\api_server.py` passed; frontend `vue-tsc --noEmit` and `npm run build` passed; runtime restart returned managed ASR/client; API status check showed `qwen3-asr-0.6b` ModelScope download state as `idle` with the expected target directory; Playwright browser smoke confirmed the Settings download modal and History layout with no console errors. The real download button was not clicked during validation, so no model files or SDK packages were installed by this run. Browser Use could not run because the installed Node is `22.21.0` while that plugin requires `>=22.22.0`, so Playwright was used as the UI fallback.

- Fixed Caps Lock real-time recording running short and sounding fast/electronic in history playback. The live drain loop no longer sleeps an extra 20ms after each blocking PyAudio read, so it can keep pace with the input stream.
- Added Caps Lock duration diagnostics: `held_seconds`, `recorded_duration_seconds`, and `capture_realtime_ratio` are logged and written to `result.json`; recordings below a 0.85 realtime ratio now emit a warning.
- Validation: Python compile passed; frontend typecheck/build passed; a direct real-device recorder smoke captured 2.000s of audio over 2.015s elapsed (`capture_realtime_ratio=0.993`) on `3.5mm麦克风 / Windows WASAPI / 48000Hz / 2ch`. The local runtime was started with `scripts/start-dev.ps1` and now reports managed ASR/client running; one user-side 3-second Caps Lock recording remains the final playback-quality confirmation.

## 2026-05-03

- Fixed the remaining Caps Lock/test-path divergence: real-time recording now carries the remembered `preferred_normalized_strategy` and channel index from the opened capture profile into the final mono normalization step, matching `/api/audio/test-input` instead of re-choosing a stereo channel/average at key release.
- Added extra capture metadata to real-time result JSON/logs so a bad recording can be compared against the exact profile and preferred normalization strategy that was used.
- Made runtime restart actions bounded: the Tauri restart command now launches the stop/start sequence in the background, the frontend stops showing an infinite spinner after a timeout, and Live UI restarts ASR/client through the API when no Tauri runtime is present.
- Added a visible top-left build marker (`version + git sha + dirty flag`) so source Live UI and stale bundled EXE builds can be distinguished immediately.
- Validation: Python compile passed; a recorder-path smoke confirmed `AudioRecorder.stop()` now honors the remembered `average` strategy; frontend typecheck/build passed; Tauri `cargo check` passed via `C:\Users\13678\.cargo\bin\cargo.exe`; Live UI browser smoke showed `Ready`, `live-ui`, and `v1.0.0+09c90ba9-dirty` with no console errors. The automated speaker-to-microphone smoke captured silence-level input in this environment, so the final Caps Lock audio-quality confirmation still needs one user-side press after the restarted client.

- Reworked the microphone capture pipeline around shared capture profiles. Real-time recording, `/api/audio/test-input`, and microphone diagnostics now probe actual device-supported formats with `2ch -> 1ch` fallback, normalize stereo captures to the cleanest mono variant, and remember per-microphone `host_api / sample_rate / capture_channels / normalized_strategy` in ignored runtime data for later reuse.
- Extended microphone test results and archive metadata with actual capture-profile facts: `capture_host_api`, `capture_channels`, `normalized_channels`, `normalized_strategy`, `normalized_channel_index`, `channel_analysis`, `stereo_correlation`, `quality_state`, and recognized preview text.
- Added `scripts/validate_audio_regression.py` to replay the user-provided reference sentence through the speaker, record it through VoiceType, transcribe the recorded WAV with the local `qwen3-asr-1.7b`, and score whether the captured sentence still matches the target phrase.
- Fixed a stereo-normalization persistence bug where `channel_0` was being written back as `-1`, preventing the remembered preferred channel from being reused on later captures.
- Validation: Python compile passed; frontend typecheck/build passed; direct model baseline still recognized the reference `.weba` sentence exactly; the regression harness validated `3.5mm麦克风 (Senary Audio) / Windows WASAPI / 48000Hz / 2ch` with the exact target sentence; a direct split-channel check on `麦克风阵列 (Senary Audio) / Windows WASAPI / 48000Hz / 2ch` also produced the exact target sentence after the channel-index fix; `/api/audio/test-input` now returns structured capture-profile data and correctly reports `太安静` when nothing is being played.

- Added `VoiceType-live-ui.bat` and `scripts/start-live-ui.ps1` as the default no-rebuild development entry. The script starts the runtime plus Vite, opens `http://127.0.0.1:55343/#/`, and avoids using stale bundled EXE assets to validate frontend fixes.
- Added a frontend source marker in the app header and Settings page so `live-ui` and `bundled-exe` are visibly different during troubleshooting.
- Changed microphone switching to hot-reload in the running recording client. Client config is now re-read while the process is alive, so shortcut, output mode, notification toggles, and microphone changes apply on the next key press instead of requiring a client restart.
- Added a shared smart input-device policy that hides NetEase/remote/virtual/mapping inputs from recommended defaults, prefers real 3.5mm/WASAPI or DirectSound microphones, and resolves saved devices by name when Windows changes PyAudio indexes after reboot.
- Fixed WASAPI 3.5mm sample-rate selection: the recorder and `/api/audio/test-input` now filter unsupported rates before opening a stream, so device `20` goes straight to `48000Hz` instead of first warning on stale `44100Hz`.
- Reduced startup UI noise by suppressing transient API connection errors during the startup grace window, and changed GPU status so it shows `检测中` until hardware/CUDA facts are loaded instead of briefly showing contradictory CPU fallback text.
- Updated Settings microphone testing to a non-reentrant recording/playback flow with a 3-second circular progress indicator for capture and playback.
- Validation: Python compile passed; frontend typecheck and production build passed; PyAudio policy smoke confirmed device `20` supports `48000Hz` only; recorder smoke remapped old index `1` to WASAPI index `20`, skipped unsupported rates, and recorded at `48000Hz`; temporary API smoke on port `55442` returned `ok=true`, `sample_rate=48000`, and a WAV preview for `/api/audio/test-input`. Browser UI smoke remains blocked because Browser's Node runtime requires `>=22.22.0` while this machine has `22.21.0`, and the fallback Playwright target was closed.

## 2026-05-02

- Added microphone advanced diagnostics: `/api/audio/scan-levels` samples every input device, returns RMS/Peak plus a compact waveform, and reports the strongest active source.
- Added a `麦克风高级检测` frontend page and Tauri command to open it as a separate desktop child window from Settings. The page can scan once or continuously monitor all detected inputs with waveform bars.
- Validation: Python compile passed; frontend typecheck/build passed; API smoke on port `55442` scanned 20 input devices, detected 5 active sources, and returned waveform arrays. Tauri build passed with `CARGO_TARGET_DIR=frontend/src-tauri/target-codex-build7`; the latest test EXE is `dist/releases/VoiceType-1.0.0/VoiceType-1.0.0-portable-build7.exe`.

- Changed Dashboard recent history actions from whole-row copy to explicit SVG buttons for play/stop and copy; recording playback is served through a task-scoped history audio API instead of exposing arbitrary file paths.
- Simplified microphone Settings: removed the full selected-device hint, removed the all-devices toggle and compact-list note, deduplicated recommended microphones by visible name, and changed microphone changes to prompt for client restart just like shortcut changes.
- Changed microphone testing to record 3 seconds, return an in-memory WAV payload, and auto-play the test audio while keeping RMS/Peak output visible.
- Added recorder startup latency logging so delayed capture can be diagnosed from `client_core` logs.
- Validation: Python compile passed; frontend typecheck/build passed; temporary API smoke confirmed `/api/audio/test-input` returns playable WAV data; Tauri build passed with `CARGO_TARGET_DIR=frontend/src-tauri/target-codex-build6`. The main portable EXE was locked by Windows, so a refreshed test EXE was written to `dist/releases/VoiceType-1.0.0/VoiceType-1.0.0-portable-build6.exe`.

- Added a desktop startup overlay that shows runtime startup stages and keeps a restart-runtime action visible if API/ASR/client startup fails.
- Added microphone diagnostics: `/api/audio/input-devices` now annotates host API, recommendation state, reason, and level-test support; `/api/audio/test-input` records a short in-memory sample and returns RMS/peak/signal status without saving audio.
- Tightened microphone handling in the recording client: selected device host API/sample rate are persisted, the recorder opens streams using the selected device's default sample rate, sends the actual sample rate to ASR, logs RMS/peak levels, and reports near-silent input as `未检测到有效麦克风输入`.
- Updated Settings with a filtered recommended microphone list, `显示全部设备`, per-device host API/sample-rate labels, and a microphone `测试` button.
- Validation: Python compile passed; frontend typecheck/build passed; temporary API smoke on `55442` returned 5 recommended devices out of 20 and opened default/WASAPI 3.5mm devices for level testing; Tauri build passed with `CARGO_TARGET_DIR=frontend/src-tauri/target-codex-build5`; portable EXE was refreshed. Full `55342` runtime restart was blocked by an old no-command-line API process that the non-admin shell could not terminate.

- Fixed startup race where `/api/start-all` launched the recording client before the ASR WebSocket was actually listening; it now waits for ASR readiness before starting the client.
- Added per-recognition WebSocket connect retry in the client so recordings made during ASR warm-up wait briefly instead of failing immediately with `[WinError 1225]`.
- Changed the current runtime configuration back to `caps_lock`; validation confirmed the client log reports `raw=caps_lock normalized=caps_lock`.
- Validation: Python compile passed; frontend typecheck/build passed; clean runtime restart returned managed server/client; service fixture ASR smoke passed 1/1 with a non-empty transcript.

- Promoted the desktop shell to version `1.0.0` across Tauri and Cargo, and added a portable release helper that creates `dist/releases/VoiceType-1.0.0/VoiceType-1.0.0-portable.exe`.
- Added Tauri single-instance handling so repeat launches focus the existing window instead of starting another runtime; tray creation now uses the configured app icon explicitly.
- Added Tauri runtime diagnostics and restart commands, plus a frontend diagnostic strip that replaces raw `Failed to fetch` with the API URL and a runtime restart action.
- Tightened desktop runtime startup: `start-runtime.ps1` now cleans project-owned old processes first, fails clearly if `55341/55342/55343` remain occupied, and API-managed server/client launches use the project `venv` Python path.
- Added microphone selection: `/api/audio/input-devices`, persisted `client.input_device_index` / `client.input_device_name`, PyAudio stream device selection with default fallback, and a Settings microphone dropdown.
- Validation: Python compile passed; frontend typecheck and production build passed; clean `start-runtime.ps1` smoke returned JSON health and input devices; browser Settings smoke showed microphone devices with no console errors; Tauri `1.0.0` build passed under `target-codex-build4`; portable EXE was created and repeat-launch smoke kept a single desktop process.

## 2026-05-01

- Reworked the recording client's global shortcut listener from polling to an event-based `keyboard.hook()` path, with normalized shortcut names for `caps_lock`, `left_shift`, `right_shift`, `shift`, and related control keys.
- Added shortcut-change confirmation in Settings: manual save now prompts to restart the recording client immediately when the shortcut changed, while autosave keeps persisting settings quietly.
- Fixed desktop-window responsiveness by allowing the Vue shell to fill the full Tauri/browser viewport and by preventing child rows/panels from forcing horizontal overflow.
- Changed Dashboard to show the latest 10 recognition records; Dashboard and History rows can now be clicked to copy their text and show a short "已复制" toast.
- Improved history text/path wrapping so long recognition text and paths wrap inside the panel instead of forcing horizontal scrolling.
- Validation: Python compile passed; hotkey normalization smoke passed for legacy and snake_case Caps Lock/Shift names; frontend typecheck and production build passed; browser smoke at `380x560` and `900x720` showed no horizontal page scroll and no console errors; Tauri build passed with `CARGO_TARGET_DIR=frontend/src-tauri/target-codex-build3`. The normal `target/release/voicetype.exe` path is still locked by no-path `voicetype.exe` processes that this non-admin shell cannot terminate.

- Fixed bundled desktop API routing so Tauri/EXE builds use `http://127.0.0.1:55342/api` and `ws://127.0.0.1:55342/ws/recognition` instead of relying on the browser dev server proxy.
- Added configurable short-press filtering with `client.min_press_seconds` defaulting to `0.1`; ignored presses are dropped before save, ASR submission, and history writes.
- Added structured daily recording archives under `data/archive/YYYY/MM/DD/HHMMSS_<task_id>/`, with `recording.wav` and `result.json` for valid real-time dictation tasks.
- Added model download URLs and `/api/models/{model_id}/open-folder`, plus Settings UI controls for missing-model downloads and opening the local model folder.
- Improved Settings with debounced auto-save, shortcut capture from physical key presses, visible save state, short-press threshold, archive-root editing, and client restart action.
- Updated latest/history result display and desktop notification success state to show recognition duration to one decimal place.
- Validation: Python compile passed; frontend typecheck and production build passed; API health/config/models smoke passed; short-press and archive JSON behavior passed a programmatic client smoke; model folder API opened the model root; Settings page browser smoke loaded at `55343`; Tauri build passed with `CARGO_TARGET_DIR=frontend/src-tauri/target-codex-build` because the normal release EXE was locked by an old `voicetype.exe` process held under Everything.

## 2026-04-30

- Completed the first Tauri desktop build after loading MSVC through `VsDevCmd.bat`; added generated Tauri icons and configured bundle icon paths.
- Produced the release desktop executable and installers: `frontend/src-tauri/target/release/voicetype.exe`, `frontend/src-tauri/target/release/bundle/msi/VoiceType_0.1.0_x64_en-US.msi`, and `frontend/src-tauri/target/release/bundle/nsis/VoiceType_0.1.0_x64-setup.exe`.
- Tightened Tauri dev server handling by enabling strict port behavior for Vite/Tauri dev, so desktop dev does not silently bind a different port when `55343` is already occupied.
- Validation: `where link` succeeds inside `VsDevCmd.bat`; frontend typecheck and production build pass; `npm run desktop:build` passes; release `voicetype.exe` starts a `VoiceType` desktop window; `/api/status` reports managed ASR/client; `/api/hardware` reports CUDA-ready RTX 5070 Ti. Full tray click validation still needs manual interaction with the visible tray icon.

- Added initial Tauri v2 desktop-shell scaffolding under `frontend/src-tauri/`, including a 480x720 main window, tray Show/Quit menu, close-to-tray behavior, and runtime start/stop hooks.
- Added `scripts/start-runtime.ps1` so a desktop shell can start or reuse the Python API, ASR server, and recording client without launching a browser frontend.
- Updated frontend API base resolution so bundled Tauri pages can call `http://127.0.0.1:55342/api` instead of a broken relative `/api` path.
- Recorded the staged packaging strategy in ADR-0004: Tauri dev shell first, portable Windows alpha second, formal installer only after runtime and model behavior are stable.
- Validation: frontend typecheck passed; frontend production build passed; `scripts/start-runtime.ps1` reported runtime ready with API/ASR/client already running. `npm install` added Tauri npm dependencies and `npm run desktop:build` downloaded Rust crates, but Tauri build is blocked because Windows MSVC linker `link.exe` is missing; `where link`, `where vswhere`, and Visual Studio Installer `vswhere.exe` checks found no usable C++ Build Tools installation.

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

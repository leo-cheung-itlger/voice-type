# PROJECT_STATUS

## Current Status

- Status: Phase 1/2 implementation in progress; Web control console is now the primary daily development/testing entry through Live UI, with persisted config, operational APIs, a working first file-transcription workspace, VoiceType-specific ports, a verified CUDA route for the installed Qwen model, a compiled Tauri 1.0.0 desktop shell for packaged releases, event-based special-key hotkey listening, runtime diagnostics, hot-reloading microphone selection, automatic microphone gain for quiet captures, Windows voice-enhanced capture as the default recording backend, and cleaned-up Settings/History archive controls.
- Active goal: stabilize VoiceType daily voice input, then expand the same frontend into Tauri with file transcription and subtitle export.
- Current blocker: none. Windows `MediaCapture` voice-mode capture tested better on the user's 3.5mm microphone and is now wired into the main recording path with fallback to PyAudio/WASAPI.
- Governance note: every substantial task now requires an explicit validation gate and browser/runtime checks for UI work.

## Current Architecture

- Python ASR server: `server/asr_server.py`, `server/asr_engine.py`
- Python input/output client: `client/client_core.py`, `client/output.py`, `client/recorder.py`
- API/control backend: `api/api_server.py`
- Shared modules: `common/`, `config/`
- Frontend: `frontend/` using Vue 3, TypeScript, Vite, Pinia, and Vue Router; designed as a compact desktop control window that now expands to the full Tauri/browser viewport without horizontal page scroll
- File transcription queue: `common/transcription.py` plus `/api/transcriptions*`, `/api/ffmpeg/status`, and `/api/llm/config`
- Runtime ports: ASR `55341`, API `55342`, frontend `55343`
- Desktop shell: `frontend/src-tauri/` uses Tauri v2, with a 480x720 window, single-instance handling, tray Show/Quit menu, close-to-tray behavior, and runtime startup through `scripts/start-runtime.ps1`
- Live UI entry: `VoiceType-live-ui.bat` starts the project runtime plus Vite at `http://127.0.0.1:55343/#/` and opens the latest source UI in a browser. Use this for daily frontend validation; use the portable EXE only when validating a packaged release.
- Daily recording archive: valid hotkey recordings now use `data/archive/YYYY/MM/DD/HHMMSS_<task_id>/recording.wav` plus `result.json`; short presses below `client.min_press_seconds` are ignored before ASR submission.
- Microphone selection: Settings reads `/api/audio/input-devices`, defaults to a deduplicated recommended physical-input list, persists `client.input_device_index`, `client.input_device_name`, `client.input_device_host_api`, `client.input_device_sample_rate`, `client.windows_voice_capture_enabled`, and `client.auto_gain_enabled`, applies client-side changes on the next key press without restart, tests microphones with the same active backend as the main recorder, and can open a separate `麦克风高级检测` window. Real-time Caps Lock recording now prefers Windows `MediaCapture` voice-mode capture (`MediaCategory=VoiceTyping`, `AudioProcessing=Default`) and automatically falls back to PyAudio/WASAPI if the helper cannot start; saved `recording.wav`, ASR input audio, and `result.json` all record the actual capture backend.
- Agent integration guide: `.agents/skills/voicetype-transcription/SKILL.md`
- Microphone processing test: `http://127.0.0.1:55343/mic-test.html`
- Windows voice capture helper: `tools/windows_voice_capture/`
- Microphone format probe: `scripts/mic_format_probe.py`
- Historical handoff: `PROJECT_SUMMARY.md`

## Validation Baseline

- Python syntax compile: passed on 2026-05-03 for the capture-profile and validation-script changes.
- Hotkey normalization smoke: passed on 2026-05-01 for legacy and snake_case `caps_lock`, `left_shift`, `right_shift`, and aggregate `shift` matching.
- Frontend typecheck and production build: passed on 2026-05-03 with `node node_modules\vue-tsc\index.js --noEmit` and `npm run build`.
- API smoke: passed on 2026-05-01 for `/api/status`, `/api/health`, `/api/config`, and `/api/models`; `/api/models` includes download links and `/api/models/{id}/open-folder` opened the expected model root.
- Browser smoke: Browser Use remains blocked because its Node runtime requires `>=22.22.0` while the installed Node is `22.21.0`; Playwright fallback passed on 2026-05-04 for Settings/History cleanup with no console errors.
- Client smoke: UI-started client stays running after startup and no longer crashes on the `websockets` `.closed` compatibility issue.
- ASR startup race smoke: `start-runtime.ps1` now waits for ASR readiness before the client is started; 2026-05-02 restart showed `server.managed=true`, `client.managed=true`, and client shortcut `caps_lock`.
- Recording feedback smoke: client-side beep/topmost desktop notification module runs without errors; Settings page exposes notification and sound toggles.
- Model smoke: selected `qwen3-asr-1.7b` resolves to the existing local CapsWriter model directory at `C:\Program Files\CapsWriter-Offline-Windows-64bit\models\Qwen3-ASR-1.7B` and loads onto `NVIDIA GeForce RTX 5070 Ti Laptop GPU` through PyTorch CUDA.
- Fixture ASR smoke: direct model recognition passed 3/3 mp3 samples; WebSocket service recognition through the current managed ASR server passed 3/3 samples on 2026-04-29 and 1/1 on 2026-05-02 after the startup race fix.
- Runtime smoke: `stop.bat` releases `55341/55342/55343`; `start.bat` starts API/frontend/ASR/client; current API reports `server.managed=true`, `client.managed=true`, and no process conflicts.
- File transcription API smoke: local ffmpeg is available at `tools/ffmpeg/bin/ffmpeg.exe`; mp3 and generated mp4 transcription tasks completed and produced JSON/TXT/SRT outputs on 2026-04-29.
- Browser transcription page smoke: `http://127.0.0.1:55343/#/transcriptions` loads, no longer shows ffmpeg missing, and has no new console errors.
- Qwen route note: `Qwen3-ASR-1.7B` is installed and remains the high-quality GPU model. Latest fixed mp3 benchmark measured `qwen3-asr-1.7b::pytorch-cuda` at about 31.79s cold load plus 4.61s inference, versus `qwen3-asr-1.7b::pytorch-cpu` at about 15.56s load plus 17.76s inference. `Qwen3-ASR-0.6B` and `Qwen3-ASR-1.7B-GGUF` are listed as low-latency/GPU candidates but are not installed locally yet.
- Benchmark harness: `scripts/model_benchmark.py` and `/api/models/benchmark-all` write per-model/mode records to ignored runtime data at `data/model_benchmark.json`, including missing-model records without fake inference timings. Paraformer CPU now initializes correctly through `OfflineRecognizer.from_paraformer` and measured about 0.16s inference, but sherpa-onnx CUDA is unavailable in the current Python environment and is blocked under `gpu_required=true`.
- Microphone diagnostics smoke: the updated `/api/audio/input-devices` on a temporary API port returned 20 total inputs and 5 recommended visible inputs, including `3.5mm麦克风` and `麦克风阵列` DirectSound/WASAPI options. `/api/audio/test-input` opened the default input, measured PCM level, returned a playable WAV payload, and correctly reported no effective signal while no one was speaking.
- Advanced microphone scan smoke: `/api/audio/scan-levels` on temporary API port `55442` scanned 20 inputs in about 1.55s, detected 5 active sources, returned waveform arrays, and showed 3.5mm/array DirectSound inputs with live RMS around 5.7% during the test window.
- Dashboard audio playback smoke: frontend build passed with recent-record play/stop and copy SVG actions. The audio file endpoint is restricted to history task recordings under VoiceType data/archive directories.
- Desktop shell smoke: MSVC Build Tools are installed and available through `VsDevCmd.bat`; Tauri 1.0.0 build passed on 2026-05-02 using `CARGO_TARGET_DIR=frontend/src-tauri/target-codex-build7`. The latest compiled EXE was copied to `dist/releases/VoiceType-1.0.0/VoiceType-1.0.0-portable-build7.exe`.
- Microphone hot-reload smoke: Python compile passed on 2026-05-03 for the shared audio device policy and client reload path; frontend typecheck/build passed; temporary API smoke on `55442` resolved the saved 3.5mm microphone from old index `1` to WASAPI index `20` while keeping NetEase virtual inputs out of recommended defaults.
- WASAPI sample-rate smoke: PyAudio confirmed 3.5mm WASAPI device `20` supports `48000Hz` and rejects `44100Hz`; recorder smoke now skips unsupported rates, records at `48000Hz`, and no longer emits the `Failed to open input stream at 44100Hz` warning. Temporary API smoke on `55442` returned `ok=true`, `sample_rate=48000`, and a WAV preview for `/api/audio/test-input`. Frontend typecheck and production build passed after the startup/GPU/mic-test UI changes.
- Audio regression smoke: on 2026-05-03 the local Qwen model still recognized the user-provided reference audio exactly; the new `scripts\validate_audio_regression.py` harness replayed that reference file through the laptop speaker and validated that `3.5mm麦克风 (Senary Audio) / Windows WASAPI / 48000Hz / 2ch` produced the exact target sentence. A direct channel split check on `麦克风阵列 (Senary Audio) / Windows WASAPI / 48000Hz / 2ch` also produced the exact target sentence once the stereo normalization bug was fixed. `/api/audio/test-input` now reports `capture_host_api`, `capture_channels`, `normalized_strategy`, `quality_state`, and `recognized_text`, and returns `太安静` instead of a false positive when nothing is being played.
- Caps Lock realtime capture smoke: passed on 2026-05-04. `AudioRecorder.stop()` honors the remembered `preferred_normalized_strategy`, the drain loop no longer sleeps an extra 20ms after each blocking read, and the client records `held_seconds`, `recorded_duration_seconds`, and `capture_realtime_ratio` for every submitted Caps Lock recording. A direct real-device recorder smoke captured 2.000s over 2.015s elapsed (`capture_realtime_ratio=0.993`) on `3.5mm麦克风 / Windows WASAPI / 48000Hz / 2ch`; final user-side check should confirm a roughly 3-second Caps Lock hold produces natural-speed playback.
- Capture auto-gain smoke: passed on 2026-05-04. Shared capture now applies default-on post-capture PCM16 auto gain after mono channel selection, targeting about `0.08` RMS with a `20dB` max gain and `0.95` peak limit. Synthetic checks confirmed quiet audio is amplified, loud audio is not further boosted, and silence remains `too_quiet`; the user-provided quiet `recording.wav` was amplified by `17.668dB` to `rms_ratio=0.079999` and `peak_ratio=0.75943`, then recognized successfully by the running `qwen3-asr-1.7b` service. `/api/audio/test-input` returned the new gain fields and correctly skipped gain for a silence-level sample.
- Windows voice capture smoke: passed on 2026-05-04 for helper/API/main-recorder integration. `tools/windows_voice_capture` builds successfully and records through Windows `MediaCapture` with `MediaCategory=VoiceTyping` and `AudioProcessing=Default`; direct helper/API-function smoke recorded `3.5mm麦克风 (Senary Audio)` as `16000Hz / 1ch / PCM16` with `rms_ratio=0.041397`; `AudioRecorder` smoke now returns `capture_backend=windows_mediacapture`; `/api/audio/test-input` now follows the same backend and returned `capture_backend=windows_mediacapture`, `sample_rate=16000`, and `quality_state=ok` on a live sample; Playwright confirmed Settings shows a default-on `Windows 语音增强采集` toggle.
- Browser microphone test smoke: passed on 2026-05-04. `/mic-test.html` is now a developer-only plain HTML page outside the VoiceType Vue app. It compares browser audio processing off/on against the current VoiceType backend recorder. `/api/audio/browser-probe` converted the user-provided `声音大小测试.webm` to `16kHz / mono / PCM16 WAV` and recognized the expected sentence through `qwen3-asr-0.6b`; `/api/audio/format-probe` still produced backend raw/channel/16k WAVs. Playwright loaded `/mic-test.html` with no console errors and confirmed the main app still has 6 bottom tabs.
- Microphone format probe smoke: passed on 2026-05-04. `scripts/mic_format_probe.py --seconds 1 --no-asr` recorded from `3.5mm麦克风 (Senary Audio) / Windows WASAPI / 48000Hz / 2ch` and wrote raw/minimal/ASR WAVs plus `result.json` under ignored `data/mic_format_tests/`. Full `--seconds 1` loaded Qwen3-ASR 1.7B on CUDA and ran recognition on channel 0, channel 1, and 16k mono candidates. The validation sample was silence-level input, so ASR text was empty by design. ffprobe confirmed `raw_48k_stereo.wav` is `pcm_s16le / 48000Hz / 2ch / 16-bit` and `standard_asr_16k_mono.wav` is `pcm_s16le / 16000Hz / 1ch / 16-bit`.
- Settings/History UX smoke: passed on 2026-05-04. Model rows now use shorter status summaries, missing Qwen/GGUF downloads open a one-click ModelScope download plus official webpage chooser, History no longer prints full archive paths in every row, and top-level/per-entry audio/result directory buttons are visible.
- Live UI workflow: added on 2026-05-03. It is now the default way to verify frontend fixes without rebuilding the Tauri EXE.

## Next Minimal Action

- Use `VoiceType-live-ui.bat` as the daily entry so the browser loads the latest frontend source without rebuilding the EXE. The header should show a visible `v1.0.0+...` build marker next to `VoiceType`.
- Use the main app Settings page to leave `Windows 语音增强采集` enabled, then do a real Caps Lock recording and inspect the newest archive `result.json` for `capture_backend=windows_mediacapture`.
- For the next new-window task, start from `PROJECT_STATUS.md`, then read `RUNBOOK.md` only if commands or validation details are needed.
- Do not use `VoiceType-1.0.0-portable-build7.exe` to validate fresh frontend changes; it contains bundled UI assets from the time it was packaged.
- For copy-paste-safe manual startup from PowerShell:
  `Set-Location -LiteralPath "C:\Users\13678\Documents\.Projects\voice-type"` then run `.\VoiceType-live-ui.bat`.

## Last Updated

- 2026-05-04

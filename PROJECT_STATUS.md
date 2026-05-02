# PROJECT_STATUS

## Current Status

- Status: Phase 1/2 implementation in progress; Web control console is now a compact desktop-window-style app with persisted config, operational APIs, a working first file-transcription workspace, VoiceType-specific ports, a verified CUDA route for the installed Qwen model, a compiled Tauri 1.0.0 desktop shell, event-based special-key hotkey listening, runtime diagnostics, and microphone selection.
- Active goal: stabilize VoiceType daily voice input, then expand the same frontend into Tauri with file transcription and subtitle export.
- Current blocker: manual Caps Lock dictation now needs user-side microphone level confirmation in Settings. The app can test an input device for RMS/peak level and will report near-silent recordings as microphone-input failures instead of generic empty ASR results. A non-admin shell could not terminate an old API process still listening on `55342`, so the newest runtime must be started after that process is closed from an elevated Task Manager or after reboot.
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
- Daily recording archive: valid hotkey recordings now use `data/archive/YYYY/MM/DD/HHMMSS_<task_id>/recording.wav` plus `result.json`; short presses below `client.min_press_seconds` are ignored before ASR submission.
- Microphone selection: Settings reads `/api/audio/input-devices`, defaults to recommended physical inputs, can show all PyAudio devices, and persists `client.input_device_index`, `client.input_device_name`, `client.input_device_host_api`, and `client.input_device_sample_rate`; the recording client applies the selected PyAudio device and actual sample rate after restart.
- Agent integration guide: `.agents/skills/voicetype-transcription/SKILL.md`
- Historical handoff: `PROJECT_SUMMARY.md`

## Validation Baseline

- Python syntax compile: passed on 2026-05-02 for the audio diagnostics/runtime changes.
- Hotkey normalization smoke: passed on 2026-05-01 for legacy and snake_case `caps_lock`, `left_shift`, `right_shift`, and aggregate `shift` matching.
- Frontend typecheck and production build: passed on 2026-05-02 with `node node_modules\vue-tsc\index.js --noEmit` and `npm run build`.
- API smoke: passed on 2026-05-01 for `/api/status`, `/api/health`, `/api/config`, and `/api/models`; `/api/models` includes download links and `/api/models/{id}/open-folder` opened the expected model root.
- Browser smoke: Playwright browser automation was unavailable in the latest validation because the browser target was closed. A dev frontend was started at `55343` with API base `55442`; API/UI builds passed, but visual browser verification remains a manual follow-up.
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
- Microphone diagnostics smoke: the updated `/api/audio/input-devices` on a temporary API port returned 20 total inputs and 5 recommended visible inputs, including `3.5mm麦克风` and `麦克风阵列` DirectSound/WASAPI options. `/api/audio/test-input` opened the default and WASAPI 3.5mm devices, measured PCM level, and correctly reported no effective signal while no one was speaking.
- Desktop shell smoke: MSVC Build Tools are installed and available through `VsDevCmd.bat`; Tauri 1.0.0 build passed on 2026-05-02 using `CARGO_TARGET_DIR=frontend/src-tauri/target-codex-build5`. The build produced `target-codex-build5/release/voicetype.exe`, MSI, and NSIS installer; `scripts/create-portable-release.ps1` refreshed `dist/releases/VoiceType-1.0.0/VoiceType-1.0.0-portable.exe`.

## Next Minimal Action

- Use `dist/releases/VoiceType-1.0.0/VoiceType-1.0.0-portable.exe` as the only manual desktop entry for current testing; do not open `target/**/deps/*.exe` or old `target-codex-build*` outputs.
- Close the stale process still holding `55342` if present, then launch `dist/releases/VoiceType-1.0.0/VoiceType-1.0.0-portable.exe`.
- In Settings, pick the `3.5mm麦克风` WASAPI `48000Hz` entry or the microphone array, click `测试`, speak for 2 seconds, and confirm it shows `有声音` before restarting the client and trying Caps Lock dictation.

## Last Updated

- 2026-05-02

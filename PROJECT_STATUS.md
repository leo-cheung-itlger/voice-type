# PROJECT_STATUS

## Current Status

- Status: Phase 1/2 implementation in progress; Web control console is now a compact desktop-window-style app with persisted config, operational APIs, a working first file-transcription workspace, VoiceType-specific ports, a verified CUDA route for the installed Qwen model, a compiled Tauri 1.0.0 desktop shell, event-based special-key hotkey listening, runtime diagnostics, and microphone selection.
- Active goal: stabilize VoiceType daily voice input, then expand the same frontend into Tauri with file transcription and subtitle export.
- Current blocker: manual Caps Lock dictation still needs user-side microphone/output confirmation after the ASR startup race fix. VoiceType now uses `55341/55342/55343`, so old CapsWriter on `52341` should no longer block this project. Qwen CUDA is working but still not sub-second; the fastest measured local model is Paraformer CPU, which is intentionally blocked by `gpu_required=true`. The recommended user entry is now the generated portable EXE under `dist/releases/VoiceType-1.0.0/`.
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
- Microphone selection: Settings reads `/api/audio/input-devices` and persists `client.input_device_index` / `client.input_device_name`; the recording client applies the selected PyAudio device after restart.
- Agent integration guide: `.agents/skills/voicetype-transcription/SKILL.md`
- Historical handoff: `PROJECT_SUMMARY.md`

## Validation Baseline

- Python syntax compile: passed on 2026-05-02.
- Hotkey normalization smoke: passed on 2026-05-01 for legacy and snake_case `caps_lock`, `left_shift`, `right_shift`, and aggregate `shift` matching.
- Frontend typecheck and production build: passed on 2026-05-02 with `node node_modules\vue-tsc\index.js --noEmit` and `npm run build`.
- API smoke: passed on 2026-05-01 for `/api/status`, `/api/health`, `/api/config`, and `/api/models`; `/api/models` includes download links and `/api/models/{id}/open-folder` opened the expected model root.
- Browser smoke: compact app loads at `http://127.0.0.1:55343/#/`; 2026-05-02 Settings smoke showed the microphone dropdown populated from `/api/audio/input-devices`, no horizontal page scroll, and no console errors.
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
- Desktop shell smoke: MSVC Build Tools are installed and available through `VsDevCmd.bat`; Tauri 1.0.0 build passed on 2026-05-02 using `CARGO_TARGET_DIR=frontend/src-tauri/target-codex-build4`. The build produced `target-codex-build4/release/voicetype.exe`, MSI, and NSIS installer; `scripts/create-portable-release.ps1` produced `dist/releases/VoiceType-1.0.0/VoiceType-1.0.0-portable.exe`, and repeat-launch smoke kept a single desktop process.

## Next Minimal Action

- Use `dist/releases/VoiceType-1.0.0/VoiceType-1.0.0-portable.exe` as the only manual desktop entry for current testing; do not open `target/**/deps/*.exe` or old `target-codex-build*` outputs.
- Run final manual daily ASR smoke with the selected microphone and default `caps_lock`: hold longer than `0.1s`, verify topmost prompt/beep, speak a short phrase, release, and confirm target output plus history/output. If output is empty, verify the selected microphone in Settings.

## Last Updated

- 2026-05-02

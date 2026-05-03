# RUNBOOK

## Setup

Use Python 3.12 and Node.js with npm.

Python dependencies are listed in `requirements.txt`.
Frontend dependencies are managed by `frontend/package-lock.json`.

Do not commit `venv/`, `frontend/node_modules/`, logs, local recordings, downloaded models, or secrets.

## Common Commands

Install Python dependencies:

```bat
python -m venv venv
venv\Scripts\python.exe -m pip install -r requirements.txt
```

Install frontend dependencies:

```bat
cd frontend
npm install
```

Start all desktop services:

```bat
start.bat
```

This first cleans project-owned duplicate processes, then launches API, frontend dev server, ASR server, and the recording client in hidden background processes. Frontend dev output is written to `logs/frontend_dev.log`; API stdout/stderr are written to `logs/api_stdout.log` and `logs/api_stderr.log`; managed ASR/client logs are written under `logs/managed_*`.

Start the latest source UI without rebuilding the EXE:

```bat
VoiceType-live-ui.bat
```

This is the default daily development/testing entry. It starts the Python runtime, starts Vite on `http://127.0.0.1:55343`, opens the browser, and shows `live-ui` in the app header/settings. Use this to validate frontend changes. The portable EXE contains bundled UI assets and should only be used when validating a packaged release.

Stop desktop services:

```bat
stop.bat
```

Start API backend only:

```bat
venv\Scripts\python.exe api\api_server.py
```

Start frontend dev server:

```bat
cd frontend
npm run dev
```

Start the current Web control console manually:

```bat
start.bat
```

Then open `http://127.0.0.1:55343/#/`. ASR server and client are started by `start.bat`; the control tab can still restart them.

Start the desktop shell, after installing Tauri dependencies:

```bat
cd frontend
npm install
npm run desktop:dev
```

The Tauri development shell opens a 480x720 desktop window, starts the Python runtime through `scripts\start-runtime.ps1`, hides to tray when the window close button is clicked, and fully exits through the tray Quit menu.

Current packaged-release entry:

```text
dist\releases\VoiceType-1.0.0\VoiceType-1.0.0-portable.exe
```

Do not use this packaged EXE to verify fresh frontend source changes unless it has just been rebuilt. Do not open EXE files from `target\release\deps`, `target\release\build`, or `target-codex-build*\deps`; those are internal build artifacts. Repeat-launching the portable EXE should focus the existing window rather than start another runtime.

Windows Tauri builds require the Microsoft MSVC linker. If `npm run desktop:build` fails with `link.exe not found`, install Visual Studio 2022 Build Tools with the C++ desktop workload, then open a new terminal and rerun the build. Check the linker with:

```bat
where link
```

If `where link` only works after loading Visual Studio's developer environment, run desktop commands through `VsDevCmd.bat`:

```bat
cmd /c "\"C:\Program Files (x86)\Microsoft Visual Studio\2022\BuildTools\Common7\Tools\VsDevCmd.bat\" -arch=x64 && cd /d C:\Users\13678\Documents\.Projects\voice-type\frontend && npm run desktop:build"
```

Build a desktop package, after the desktop shell has passed validation:

```bat
cd frontend
npm run desktop:build
```

Current Windows build outputs:

- `frontend\src-tauri\target\release\voicetype.exe`
- `frontend\src-tauri\target\release\bundle\msi\VoiceType_1.0.0_x64_en-US.msi`
- `frontend\src-tauri\target\release\bundle\nsis\VoiceType_1.0.0_x64-setup.exe`
- `dist\releases\VoiceType-1.0.0\VoiceType-1.0.0-portable.exe`

Do not treat the first package as a final installer. The first target should be a portable alpha package used from this project tree, with external models and the existing `venv`. A formal installer should come after runtime lifecycle, model selection, and update behavior are stable.

If `npm run desktop:build` fails because `frontend\src-tauri\target\release\voicetype.exe` is locked, close all running VoiceType windows and tray instances. If another process such as Everything still holds the executable, build into a temporary target directory:

```bat
set CARGO_TARGET_DIR=C:\Users\13678\Documents\.Projects\voice-type\frontend\src-tauri\target-codex-build
cmd /c "\"C:\Program Files (x86)\Microsoft Visual Studio\2022\BuildTools\Common7\Tools\VsDevCmd.bat\" -arch=x64 && cd /d C:\Users\13678\Documents\.Projects\voice-type\frontend && npm run desktop:build"
```

The temporary EXE is written to `frontend\src-tauri\target-codex-build\release\voicetype.exe`. Additional temporary targets matching `frontend\src-tauri\target-codex-build*` are ignored by Git.

Create the current portable release from a successful Tauri release build:

```bat
powershell -NoProfile -ExecutionPolicy Bypass -File scripts\create-portable-release.ps1 -Root C:\Users\13678\Documents\.Projects\voice-type -Version 1.0.0 -TargetRelease C:\Users\13678\Documents\.Projects\voice-type\frontend\src-tauri\target-codex-build4\release
```

## Validation Order

Every task must have an explicit validation gate. For implementation work, do not stop at "server started" or "build passed" when the user-facing behavior needs runtime confirmation.

1. Python syntax compile:

```bat
venv\Scripts\python.exe -m py_compile api\api_server.py server\asr_server.py server\asr_engine.py client\client_core.py client\output.py client\recorder.py common\history.py common\hotword.py common\logger.py config\settings.py test_asr.py test_qwen_direct.py download_model.py
```

2. Frontend typecheck:

```bat
cd frontend
node node_modules\vue-tsc\index.js --noEmit
```

3. Frontend production build:

```bat
cd frontend
npm run build
```

4. API smoke test:

```bat
venv\Scripts\python.exe api\api_server.py
```

Then verify:

- `http://127.0.0.1:55342/api/status`
- `http://127.0.0.1:55342/api/health`
- `http://127.0.0.1:55342/api/config`
- `http://127.0.0.1:55342/api/models`
- `http://127.0.0.1:55342/api/hardware`

5. ASR smoke test:

```bat
venv\Scripts\python.exe test_asr.py
```

This requires local model files and the expected audio/model environment.

Fixed fixture ASR smoke:

```bat
venv\Scripts\python.exe scripts\asr_fixture_smoke.py --mode direct --limit 3
venv\Scripts\python.exe scripts\asr_fixture_smoke.py --mode service --limit 3 --timeout 180
```

Direct mode loads Qwen3-ASR and transcribes mp3 files from the CapsWriter assets directory. Service mode sends decoded PCM audio through the managed WebSocket ASR server and verifies the server response.

Model benchmark harness:

```bat
venv\Scripts\python.exe scripts\model_benchmark.py
```

The harness runs every configured model/mode plan and writes `data/model_benchmark.json`. Missing model directories are recorded as missing records without inference. To target specific models or audio:

```bat
venv\Scripts\python.exe scripts\model_benchmark.py --models qwen3-asr-1.7b paraformer --audio-file C:\Media\sample.mp3
```

Targeted CPU/GPU benchmark through the API:

```bat
curl -X POST http://127.0.0.1:55342/api/models/benchmark -H "Content-Type: application/json" -d "{\"model\":\"qwen3-asr-1.7b\",\"acceleration\":\"pytorch-cuda\"}"
curl -X POST http://127.0.0.1:55342/api/models/benchmark -H "Content-Type: application/json" -d "{\"model\":\"qwen3-asr-1.7b\",\"acceleration\":\"pytorch-cpu\"}"
curl -X POST http://127.0.0.1:55342/api/models/benchmark -H "Content-Type: application/json" -d "{\"model\":\"paraformer\",\"acceleration\":\"sherpa-onnx-cpu\"}"
```

GPU policy:

- Default runtime policy is `gpu_required=true` and `allow_cpu_fallback=false`.
- If the selected backend cannot use GPU, ASR startup or benchmark must fail with a clear error instead of silently using CPU.
- Current verified GPU route is `qwen3-asr-1.7b::pytorch-cuda`.
- Current very fast route is `paraformer::sherpa-onnx-cpu`, but it is not recommended while GPU is required.

## Acceptance Harness

For frontend/control-console changes:

1. Run Python compile and frontend build.
2. Start Live UI with `VoiceType-live-ui.bat`.
3. Open `http://127.0.0.1:55343/#/` in a browser and confirm the header or Settings page shows `live-ui`.
4. Check console errors and visible UI layout.
5. Visit Control, History, Hotwords, Stats, and Settings tabs.
6. Verify API-driven fields load instead of silently showing defaults.

For API changes:

1. Start API.
2. Verify `/api/status`, `/api/health`, `/api/config`, `/api/models`.
3. If the change touches hotwords, verify hotword read/write/reload.
4. If the change touches process control, verify start/stop responses and status refresh.

For daily ASR changes:

1. Start the Web control console.
2. Start ASR server and client from the console.
3. Press the configured shortcut key, record a short phrase, and release. The default is `caps_lock`.
4. Confirm recognition result appears in the target input, the Web console latest result, and history.
5. Confirm saved audio path is present when recording save is enabled.
6. Restart server/client and confirm status recovers.
7. If recording notifications are enabled, confirm a topmost desktop prompt and a short beep appear on start and finish.

Special-key shortcut checks:

1. Use Settings to record or enter `caps_lock`, click Save, then choose whether to restart the recording client.
2. After the client restarts, hold Caps Lock longer than `client.min_press_seconds` and confirm the client log contains hook startup plus shortcut down/up events.
3. Repeat with `right_shift`; right Shift should trigger, left Shift should not.
4. Repeat with aggregate `shift`; both left and right Shift should trigger.
5. Tap faster than the threshold and confirm the log records an ignored short press with no ASR submission.

ASR startup readiness checks:

1. Run `scripts\stop-dev.ps1`, then `scripts\start-runtime.ps1`.
2. Confirm `start-runtime.ps1` waits until `/api/status` reports `server.port_open=true` before the client starts.
3. The client log should not show `[WinError 1225]` after a clean start.
4. If a recording is made while ASR is warming up, the client should retry the WebSocket connection briefly instead of dropping the request immediately.

Short-press and archive checks:

1. Confirm `/api/config` exposes `client.min_press_seconds` and `client.archive_root`.
2. Tap the shortcut faster than the threshold; no audio, ASR request, history row, or archive directory should be produced.
3. Hold the shortcut longer than the threshold; the task should create `data\archive\YYYY\MM\DD\HHMMSS_<task_id>\recording.wav` and `result.json`.
4. The topmost prompt should move from recording to analyzing with seconds, then success with a one-decimal duration.
5. History and Dashboard should show the result duration to one decimal place.

Microphone selection checks:

1. `GET /api/audio/input-devices` should return `available=true`, a `devices` list, and `recommended_count`.
2. Settings should show a short recommended list by default. `3.5mm麦克风` and `麦克风阵列` should be visible if Windows exposes them through DirectSound/WASAPI. Use `显示全部设备` only for troubleshooting duplicates.
3. Selecting a device persists `client.input_device_index`, `client.input_device_name`, `client.input_device_host_api`, and `client.input_device_sample_rate`. The running client hot-reloads these values and applies them on the next key press; restart the client only as a recovery action.
4. Click `测试`, speak for about 3 seconds, and confirm the UI shows one recording progress circle followed by one playback progress circle. The button must stay disabled until playback finishes, and the captured sample should auto-play once.
5. Confirm the test result says `有声音` with non-trivial RMS/Peak values. For WASAPI 3.5mm device `20`, `/api/audio/test-input` should return `sample_rate=48000` and a WAV preview.
6. Press the shortcut after saving and confirm `logs\recorder_*.log` reports the chosen device index/name and actual sample rate without requiring a restart. For device `20`, logs should show `rate=48000` and should not show `Failed to open input stream at 44100Hz`.
7. If Windows changes device indexes after reboot, the client should remap the saved device by name/host API. If the saved device is missing, recording should fall back to the smart default, preferring real 3.5mm/WASAPI or DirectSound microphones and avoiding NetEase/remote/virtual/mapping inputs.
8. If a real-time recording has near-zero RMS/Peak, the client should show `未检测到有效麦克风输入` and skip ASR submission.

Mic test API:

```bat
curl -X POST http://127.0.0.1:55342/api/audio/test-input -H "Content-Type: application/json" -d "{\"device_index\":20,\"seconds\":3}"
```

The API records only an in-memory sample, filters unsupported sample rates before opening the stream, returns RMS/Peak plus a base64 WAV preview for UI playback, and does not save a recording file.

Advanced microphone monitor:

```bat
curl -X POST http://127.0.0.1:55342/api/audio/scan-levels -H "Content-Type: application/json" -d "{\"seconds\":0.2,\"include_all\":true,\"waveform_points\":64}"
```

Settings has a `高级检测` button. In the desktop shell it opens a separate microphone monitor window; in browser/dev mode it falls back to the `/microphones` route. The monitor samples every input device, shows RMS/Peak and a compact waveform, and can save the chosen device to config. After choosing a device, test Caps Lock dictation again; the running client should pick up the change on the next key press.

History and layout checks:

1. Dashboard should show the latest 10 records when available.
2. Left-clicking a Dashboard or History row should copy that row's text and show the `已复制` toast.
3. Delete, mark, and other row buttons must not trigger row copy.
4. Test `380x560`, `480x720`, and `900x720`; the shell should fill the viewport and `document.documentElement.scrollWidth` should not exceed `clientWidth`.
5. Long history text and path fields should wrap inside their panel without horizontal page scrolling.

If a step cannot run because local model files, microphone access, GPU, or OS interaction is unavailable, record the exact blocked step and the manual command needed.

## File Transcription

VoiceType exposes a separate file transcription queue so long audio/video jobs do not share the real-time right-Shift client path.

Check ffmpeg:

```bat
curl http://127.0.0.1:55342/api/ffmpeg/status
```

ffmpeg is resolved in this order:

1. `VOICETYPE_FFMPEG_PATH` / `VOICETYPE_FFPROBE_PATH`
2. System `PATH`
3. Project-local `tools\ffmpeg\bin\ffmpeg.exe`

Create a path-based transcription task:

```bat
curl -X POST http://127.0.0.1:55342/api/transcriptions ^
  -H "Content-Type: application/json" ^
  -d "{\"input_files\":[\"C:\\Media\\demo.mp4\"],\"formats\":[\"json\",\"txt\",\"srt\"],\"polish\":false}"
```

Poll task status and outputs:

```bat
curl http://127.0.0.1:55342/api/transcriptions
curl http://127.0.0.1:55342/api/transcriptions/<task_id>
curl http://127.0.0.1:55342/api/transcriptions/<task_id>/outputs
```

Configure OpenAI-compatible polishing:

```bat
curl -X PUT http://127.0.0.1:55342/api/llm/config ^
  -H "Content-Type: application/json" ^
  -d "{\"base_url\":\"https://api.openai.com/v1\",\"model\":\"gpt-4.1-mini\",\"api_key\":\"...\",\"temperature\":0.2}"
```

Browser drag/drop uploads files to ignored local runtime storage under `data/transcription_uploads/`. Path-based tasks preserve the default behavior of exporting to a sibling `<source>_transcript` folder. A later Tauri shell can pass drag/drop source paths directly to the same HTTP API.

File transcription validation:

1. `GET /api/ffmpeg/status` must report `available=true` before mp3/mp4 decode tests can pass.
2. Submit at least one mp3 and one mp4 task with `formats=["json","txt","srt"]`.
3. Confirm the task reaches `completed` and output paths exist.
4. With no LLM API key, confirm the UI disables polishing or the API returns a clear configuration error.
5. With a valid OpenAI-compatible key, submit a short task with `polish=true` and confirm polished TXT/SRT outputs are created.

## Desktop Packaging

Current desktop direction:

1. Tauri dev shell: real desktop window over the existing Vue frontend.
2. Portable Windows alpha: a zip/folder build that can be opened and deleted without installing system entries.
3. Windows installer: only after the Python runtime, model paths, tray lifecycle, logs, and updater strategy are stable.
4. macOS build: build on macOS or a macOS CI runner; do not expect reliable Windows-to-macOS cross-compilation.

Desktop validation:

1. `cd frontend && npm run build`
2. `cd frontend && npm run desktop:dev`
3. Confirm the window opens at about 480x720.
4. Confirm `/api/status` returns managed server/client.
5. Click the window close button and confirm it hides instead of killing runtime.
6. Restore from tray.
7. Use tray Quit and confirm `55341/55342/55343` are no longer listening.

## Failure Notes

- In PowerShell, `npm` may fail if script execution policy blocks `npm.ps1`; use `cmd /c npm run build` or a normal Command Prompt.
- In the Codex sandbox, Vite/esbuild may fail with `spawn EPERM`; rerun the build in a normal local terminal.
- Qwen3-ASR initialization is configured for offline local model paths under the parent-level `models/` directory.
- If CUDA is unavailable and `gpu_required=true`, Qwen3-ASR must fail startup instead of falling back to CPU. Only set `allow_cpu_fallback=true` for explicit CPU debugging.
- PyTorch CUDA verification:

```bat
venv\Scripts\python.exe -c "import torch; print(torch.__version__); print(torch.version.cuda); print(torch.cuda.is_available()); print(torch.cuda.get_device_name(0) if torch.cuda.is_available() else '')"
```
- VoiceType uses ASR/API/frontend ports `55341/55342/55343`. Old CapsWriter may still own `52341`, but that should no longer block this project. If `/api/status` reports conflicts on `55341`, run `stop.bat` and then `start.bat`.
- If `scripts\start-runtime.ps1` says `55342` is still occupied and normal `stop.bat` cannot terminate the owner, check the PID with:

```powershell
Get-NetTCPConnection -LocalPort 55342 -State Listen | Select-Object LocalPort,OwningProcess
Get-Process -Id <PID> | Select-Object Id,ProcessName,Path,StartTime
```

If `taskkill /PID <PID> /F` returns `Access is denied`, close VoiceType from an elevated Task Manager or reboot before launching the newest portable EXE. Do not start another EXE while the stale API process remains.
- UI-managed server/client processes should not open black console windows; their logs are under `logs/managed_server_*.log` and `logs/managed_client_*.log`.
- Settings saved from the Web console are written to `data/app_config.json`, which is intentionally ignored by Git.

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

Start the current Web control console:

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
- `frontend\src-tauri\target\release\bundle\msi\VoiceType_0.1.0_x64_en-US.msi`
- `frontend\src-tauri\target\release\bundle\nsis\VoiceType_0.1.0_x64-setup.exe`

Do not treat the first package as a final installer. The first target should be a portable alpha package used from this project tree, with external models and the existing `venv`. A formal installer should come after runtime lifecycle, model selection, and update behavior are stable.

If `npm run desktop:build` fails because `frontend\src-tauri\target\release\voicetype.exe` is locked, close all running VoiceType windows and tray instances. If another process such as Everything still holds the executable, build into a temporary target directory:

```bat
set CARGO_TARGET_DIR=C:\Users\13678\Documents\.Projects\voice-type\frontend\src-tauri\target-codex-build
cmd /c "\"C:\Program Files (x86)\Microsoft Visual Studio\2022\BuildTools\Common7\Tools\VsDevCmd.bat\" -arch=x64 && cd /d C:\Users\13678\Documents\.Projects\voice-type\frontend && npm run desktop:build"
```

The temporary EXE is written to `frontend\src-tauri\target-codex-build\release\voicetype.exe`.

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
2. Start API and frontend.
3. Open `http://127.0.0.1:55343/#/` in a browser.
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
3. Press the configured shortcut key, record a short phrase, and release. The default may be `caps_lock`; the current test config uses `right shift`.
4. Confirm recognition result appears in the target input, the Web console latest result, and history.
5. Confirm saved audio path is present when recording save is enabled.
6. Restart server/client and confirm status recovers.
7. If recording notifications are enabled, confirm a topmost desktop prompt and a short beep appear on start and finish.

Short-press and archive checks:

1. Confirm `/api/config` exposes `client.min_press_seconds` and `client.archive_root`.
2. Tap the shortcut faster than the threshold; no audio, ASR request, history row, or archive directory should be produced.
3. Hold the shortcut longer than the threshold; the task should create `data\archive\YYYY\MM\DD\HHMMSS_<task_id>\recording.wav` and `result.json`.
4. The topmost prompt should move from recording to analyzing with seconds, then success with a one-decimal duration.
5. History and Dashboard should show the result duration to one decimal place.

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
- UI-managed server/client processes should not open black console windows; their logs are under `logs/managed_server_*.log` and `logs/managed_client_*.log`.
- Settings saved from the Web console are written to `data/app_config.json`, which is intentionally ignored by Git.

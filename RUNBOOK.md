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

This launches the API and frontend dev server in hidden background processes. Frontend dev output is written to `logs/frontend_dev.log`; API stdout/stderr are written to `logs/api_stdout.log` and `logs/api_stderr.log`.

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

Then open `http://127.0.0.1:52343/#/` and start the ASR server/client from the control tab.

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

- `http://127.0.0.1:52342/api/status`
- `http://127.0.0.1:52342/api/health`
- `http://127.0.0.1:52342/api/config`
- `http://127.0.0.1:52342/api/models`

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

## Acceptance Harness

For frontend/control-console changes:

1. Run Python compile and frontend build.
2. Start API and frontend.
3. Open `http://127.0.0.1:52343/#/` in a browser.
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

If a step cannot run because local model files, microphone access, GPU, or OS interaction is unavailable, record the exact blocked step and the manual command needed.

## Failure Notes

- In PowerShell, `npm` may fail if script execution policy blocks `npm.ps1`; use `cmd /c npm run build` or a normal Command Prompt.
- In the Codex sandbox, Vite/esbuild may fail with `spawn EPERM`; rerun the build in a normal local terminal.
- Qwen3-ASR initialization is configured for offline local model paths under the parent-level `models/` directory.
- If CUDA is unavailable, Qwen3-ASR should remain on CPU instead of failing startup.
- If CapsWriter is already running and `start_server.exe` owns port `52341`, the Web console will show the ASR server as an external unmanaged service. Close that old process from an elevated Task Manager/terminal or use a different ASR port before validating the current repo's managed server.
- UI-managed server/client processes should not open black console windows; their logs are under `logs/managed_server_*.log` and `logs/managed_client_*.log`.
- Settings saved from the Web console are written to `data/app_config.json`, which is intentionally ignored by Git.

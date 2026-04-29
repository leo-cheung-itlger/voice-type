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

## Validation Order

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

Then open `http://127.0.0.1:52342/api/status`.

5. ASR smoke test:

```bat
venv\Scripts\python.exe test_asr.py
```

This requires local model files and the expected audio/model environment.

## Failure Notes

- In PowerShell, `npm` may fail if script execution policy blocks `npm.ps1`; use `cmd /c npm run build` or a normal Command Prompt.
- In the Codex sandbox, Vite/esbuild may fail with `spawn EPERM`; rerun the build in a normal local terminal.
- Qwen3-ASR initialization is configured for offline local model paths under the parent-level `models/` directory.

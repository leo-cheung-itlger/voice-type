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
venv\Scripts\python.exe -m pip install --require-hashes -r requirements-cpu.lock
```

Install frontend dependencies:

```bat
cd frontend
npm ci
```

Start all desktop services:

```bat
start.bat
```

This cleans only project-owned processes, then starts API and the frontend in hidden background processes. Select/download a model in Settings and apply it to start ASR and the recording client. Opening the UI never requires a loaded model. Frontend dev output is written to `logs/frontend_dev.log`; API stdout/stderr are written to `logs/api_stdout.log` and `logs/api_stderr.log`; managed ASR/client logs are written under `logs/managed_*`.

Start the latest source UI without rebuilding the EXE:

```bat
VoiceType-live-ui.bat
```

This is the default daily development/testing entry. It starts the Python runtime, starts Vite on `http://127.0.0.1:55343`, opens the browser, and shows a short version plus a clickable model in the header. Build identity and PID are under advanced diagnostics. Use this to validate frontend changes. The portable EXE contains bundled UI assets and should only be used when validating a packaged release.

If the runtime restart button is needed, it should return control to the UI instead of spinning indefinitely. Live UI restarts ASR/client through the API; the Tauri shell starts the stop/start sequence in the background and the frontend polls readiness with a visible timeout.

Validate the microphone regression harness against the user-provided reference sentence:

```bat
venv\Scripts\python.exe scripts\validate_audio_regression.py
```

This converts the reference `.weba` file to `48k mono`, plays it through the current speaker output, records from the requested microphones, runs the recorded WAV back through the local `qwen3-asr-1.7b`, and writes validation WAVs under `data\transcription_validation\audio_regression\`. Use the `3.5mm` microphone for speaker-facing playback validation; the laptop array microphone should be validated in its real physical position, not forced to share the same speaker geometry. Caps Lock validation should report the active `capture_backend`, the remembered `normalized_strategy`/channel preference for PyAudio fallback cases, and, when Windows voice capture is disabled, default-on `auto_gain_enabled=true` should apply post-capture gain only when effective signal is present.

Probe ASR WebSocket latency with the latest archived recording:

```bat
venv\Scripts\python.exe scripts\asr_latency_probe.py --mode batch
venv\Scripts\python.exe scripts\asr_latency_probe.py --mode chunked --chunk-ms 50
venv\Scripts\python.exe scripts\asr_latency_probe.py --mode realtime --chunk-ms 50
```

`batch` sends the whole WAV in one WebSocket message, `chunked` sends 50ms-style chunks without waiting between chunks, and `realtime` sleeps between chunks to simulate recording-time streaming. The current ASR server still starts recognition on `audio_end`; this probe measures transport and post-end wait, and is the acceptance tool for any future true streaming client/server change.

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

Then open `http://127.0.0.1:55343/#/`. Use Settings → 应用并重启识别, then Control → 启动. Model and language changes are transactional and cannot interrupt an active recording/task.

Start the desktop shell, after installing Tauri dependencies:

```bat
cd frontend
npm ci
npm run desktop:dev
```

The Tauri development shell opens a 480x720 desktop window, starts the Python runtime through `scripts\start-runtime.ps1`, hides to tray when the window close button is clicked, and fully exits through the tray Quit menu.

便携构建流程见下方唯一的 Desktop Packaging 章节。开发 UI 使用 VoiceType-live-ui.bat；发布验收使用刚构建的完整目录，不能单独复制 EXE 或从 Rust 的 deps/build 目录启动。

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
- `http://127.0.0.1:55342/api/audio/test-input` with a real microphone selected; when `Windows 语音增强采集` is enabled, this should usually report `capture_backend=windows_mediacapture`, `sample_rate=16000`, and `host_api=Windows MediaCapture`

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
7. On Settings, missing-model rows should stay short and the Download action should show one-click ModelScope download plus official model webpage options when configured.
8. On History, rows should hide full archive paths by default, show `推理 x.xs`, and expose top-level/per-entry audio/result directory buttons.

For API changes:

1. Start API.
2. Verify `/api/status`, `/api/health`, `/api/config`, `/api/models`.
3. If the change touches model download, verify `GET /api/models/{model_id}/download-modelscope` reports the expected install directory. Only click the POST-backed one-click download when the user explicitly wants to install/download the model.
4. If the change touches history archive paths, verify folder-open endpoints remain constrained to VoiceType archive/data roots and only open existing files/folders.
5. If the change touches hotwords, verify hotword read/write/reload.
6. If the change touches process control, verify start/stop responses and status refresh.
7. If the change touches audio capture, verify `/api/audio/test-input` returns the actual `capture_backend`, `capture_host_api`, `sample_rate`, `capture_channels`, `normalized_strategy`, `quality_state`, `recognized_text`, `volume_policy`, `gain_db`, and `input_output_gain_ratio`.

For daily ASR changes:

1. Start the Web control console.
2. Start ASR server and client from the console.
3. Press the configured shortcut key, record a short phrase, and release. The default is `caps_lock`.
4. Confirm recognition result appears in the target input, the Web console latest result, and history.
5. Confirm saved audio path is present when recording save is enabled.
6. Restart server/client and confirm status recovers.
7. If recording notifications are enabled, confirm a topmost desktop prompt and a short beep appear on start and finish.
8. For Caps Lock audio-quality checks, hold the shortcut for about 3 seconds and inspect the newest `result.json`: it should record `capture_backend`, `device_name`, `sample_rate`, and `audio_level`; if Windows voice capture is enabled the backend should be `windows_mediacapture`, and if it is disabled the PyAudio path should still show `capture_realtime_ratio` at least `0.85` plus the expected auto-gain fields.

Microphone regression checks:

1. Run `venv\Scripts\python.exe scripts\validate_audio_regression.py`.
2. Confirm the baseline direct-model recognition of the reference file still matches `你好，请问听得到我说话吗？这边正在测试麦克风`.
3. Confirm the `3.5mm麦克风 (Senary Audio)` best result is `Windows WASAPI / 48000Hz / 2ch` with the exact target sentence.
4. For the laptop array microphone, validate in its normal physical position; do not require the same speaker-facing geometry as the external 3.5mm microphone.
5. After a passing run, restart the runtime so the remembered capture profiles are picked up by the live recording client.

Microphone format probe:

Browser processing test page:

```text
http://127.0.0.1:55343/mic-test.html
```

Start Live UI, open the standalone page above, choose a duration, then click `开始测试`. This page is intentionally outside the VoiceType Vue app and should not appear in the main bottom navigation. It records browser capture with audio processing off, browser capture with audio processing on, the current VoiceType PyAudio/WASAPI backend recorder, and Windows MediaCapture voice-mode capture, then shows players plus RMS/Peak and ASR text.

Windows voice capture helper:

```powershell
$env:DOTNET_CLI_HOME = "$PWD\data\dotnet_home"
$env:DOTNET_SKIP_FIRST_TIME_EXPERIENCE = "1"
$env:DOTNET_NOLOGO = "1"
dotnet build tools\windows_voice_capture\VoiceCaptureHelper.csproj -c Release -p:Platform=x64
dotnet tools\windows_voice_capture\bin\x64\Release\net10.0-windows10.0.26100.0\VoiceCaptureHelper.dll --seconds 3 --output data\mic_format_tests\windows_voice_manual.wav --device-name "3.5mm麦克风" --category VoiceTyping --processing Default
```

The helper writes `16kHz / mono / PCM16 WAV` using Windows `MediaCapture` with `MediaCategory=VoiceTyping` and `AudioProcessing=Default`. This path is now the default main-recorder backend when `Windows 语音增强采集` is enabled in Settings; the standalone page remains the developer comparison tool.

CLI equivalent:

```bat
venv\Scripts\python.exe scripts\mic_format_probe.py --seconds 5
```

The CLI path records one sample from the selected input and writes comparison WAVs under ignored `data\mic_format_tests\YYYYMMDD-HHMMSS...\`: raw capture, fixed channel mono candidates, and a `16kHz` mono ASR candidate. It also writes `result.json` with RMS/Peak metrics and recognition results unless ASR is skipped. Use the browser page when diagnosing Windows/browser audio processing; use the CLI when diagnosing raw microphone level, channel choice, or ASR preprocessing.

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
6. For normal dictation, `recording.wav` playback should have natural speed and pitch; if it sounds fast/electronic, compare `held_seconds`, `recorded_duration_seconds`, and `capture_realtime_ratio` in `result.json` before changing playback code.

Microphone selection checks:

1. `GET /api/audio/input-devices` should return `available=true`, a `devices` list, and `recommended_count`.
2. Settings should show a short recommended list by default. `3.5mm麦克风` and `麦克风阵列` should be visible if Windows exposes them through DirectSound/WASAPI. Use `显示全部设备` only for troubleshooting duplicates.
3. Selecting a device persists `client.input_device_index`, `client.input_device_name`, `client.input_device_host_api`, and `client.input_device_sample_rate`. The running client hot-reloads these values and applies them on the next key press; restart the client only as a recovery action.
4. Click `测试`, speak for about 3 seconds, and confirm the UI shows one recording progress circle followed by one playback progress circle. The button must stay disabled until playback finishes, and the captured sample should auto-play once.
5. Confirm the test result says `有声音` with non-trivial RMS/Peak values. With `Windows 语音增强采集` enabled, `/api/audio/test-input` should return `capture_backend=windows_mediacapture`, `sample_rate=16000`, and a WAV preview; with the setting disabled, the same endpoint should return the current PyAudio/WASAPI profile such as `48000Hz`.
6. Press the shortcut after saving and confirm `logs\recorder_*.log` reports the chosen backend, device name, and actual sample rate without requiring a restart. For Windows voice capture, logs should mention `Recording started with Windows voice capture`; for the PyAudio fallback path, device `20` should still show `rate=48000` and should not show `Failed to open input stream at 44100Hz`.
7. Confirm saved/test WAVs choose the expected emitted path. With Windows voice capture enabled, the emitted audio should be `16kHz / mono / PCM16` and report `volume_policy=windows_mediacapture_default_processing`; with the PyAudio path, saved/ASR mono audio must still use a real `channel_N` strategy and, when `client.auto_gain_enabled=true`, quiet but valid speech should report `volume_policy=auto_gain_limited`, `gain_db`, `source_audio_level`, and `processed_audio_level`.
8. If Windows changes device indexes after reboot, the client should remap the saved device by name/host API. If the saved device is missing, recording should fall back to the smart default, preferring real 3.5mm/WASAPI or DirectSound microphones and avoiding NetEase/remote/virtual/mapping inputs.
9. If a real-time recording has near-zero RMS/Peak, the client should show `未检测到有效麦克风输入` and skip ASR submission.

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

构建机需要 Python 3.12 x64、Node/npm、Rust、MSVC C++ Build Tools 和 .NET SDK。最终用户不需要这些开发工具。

```powershell
cd frontend
npm ci
npm run desktop:build -- --no-bundle
cd ..
.\scripts\create-portable-release.ps1 -Version 1.0.0-alpha.1 -TargetRelease frontend\src-tauri\target\release -WithCuda
```

如使用 CARGO_TARGET_DIR，传入相应 release 目录。找不到 MSVC linker 时，在 Visual Studio Developer PowerShell 中执行构建。构建会发布自包含 Windows 录音增强组件，再打包官方 CPython 3.12.10 与 hash-locked 依赖。默认从 wheel 安装；`-UseInstalled` 可复制已安装且版本、RECORD 哈希匹配的锁定依赖，用于复现本机测试环境。

产物为 dist/releases/VoiceType-<version>-windows-x64.zip、可选 CUDA ZIP／分卷及 VoiceType-<version>-components.json。CPU ZIP 不含模型和 PyTorch。下载运行组件只允许与 portable.json 对应的 GitHub tag；尚无该预发行时下载会明确失败。上传时同时提供 manifest 和 CUDA ZIP（或全部分卷），遵守单文件大小限制。

打包前在 tools/ffmpeg/ 提供该二进制的 LICENSE.txt、SOURCE.txt，并完成第三方再分发材料；只有网址不足以替代适用许可证要求的对应源码。项目源码许可尚需维护者选择，参考 THIRD_PARTY.md。

发布验收顺序：

1. 解压到新的中文、空格目录；无系统 Python、无 PyTorch、无开发目录的 Windows 10/11 环境打开界面，确认不加载模型也可进入设置。
2. 点击下载 SenseVoice（约 163 MB），检查路径、进度、重试、导入、校验错误；应用 CPU + 普通话，测试 F1（或用户设置的键）录音到目标应用输入。
3. 普通话／自动／英语／粤语使用相同样本对照；测试不支持组合、录音期间切换、加载失败恢复、停止再启动。
4. 文件转录保存语言快照，复用相同服务；换模型任务暂停输入，结束后恢复。检查 TXT/JSON/SRT。
5. NVIDIA 机器安装可选组件和 Qwen 0.6B，实测正常、显存不足、驱动不兼容；自动模式提供 CPU 恢复，严格 GPU 明确失败。
6. 记录模型冷加载、首次／预热识别、进程内存和 CUDA 分配；低配实机单独报告。
7. 469×719 和桌面窗口检查模型入口、中文状态、错误恢复、控制台；测试托盘隐藏、恢复、退出和重复启动。
8. WebView2 缺失时按 README 的 Microsoft 官方链接安装；增强录音不可用时确认基础录音回退。确认数据均在便携目录。
9. 完成第三方材料和全部必需验收后才创建 GitHub 预发行。未验证项目留在 PROJECT_STATUS.md，不能用构建通过替代。

运行回归：

```powershell
.\venv\Scripts\python.exe -m unittest discover -s tests -v
.\venv\Scripts\python.exe scripts\validate_runtime.py --fixtures <含zh.wav/en.wav/yue.wav目录> --model sensevoice --mode cpu --output data/portable-validation/cpu.json
```

硬件／语言／便携策略的当前验证状态只在 PROJECT_STATUS.md 维护。

## Failure Notes

- In PowerShell, `npm` may fail if script execution policy blocks `npm.ps1`; use `cmd /c npm run build` or a normal Command Prompt.
- In the Codex sandbox, Vite/esbuild may fail with `spawn EPERM`; rerun the build in a normal local terminal.
- Qwen3-ASR initialization is configured for offline local model paths under the parent-level `models/` directory.
- Use compute_mode auto/cpu/cuda instead of editing the legacy GPU flags. Strict cuda fails explicitly; auto may recover to installed SenseVoice with a visible reason. Model/language changes must use /api/models/apply.
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

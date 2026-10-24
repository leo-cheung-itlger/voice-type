# VoiceType

<p align="center">
  <img src="frontend/src-tauri/icons/icon.png" alt="VoiceType logo" width="128">
</p>

<p align="center">
  <strong>Private, local voice input for Windows.</strong><br>
  Hold a hotkey, speak, and get text at the cursor. Recognition runs on your own computer.
</p>

<p align="center">
  <a href="README.zh-CN.md">阅读中文版</a> ·
  <a href="https://github.com/leo-cheung-itlger/voice-type">GitHub repository</a>
</p>

> **Alpha status:** VoiceType is an open source development test. A clean Windows 10/11 installation, low-end hardware coverage, and a one-click public installer are still being validated. Please treat this as an early test build rather than a finished release.

## What VoiceType does

VoiceType is a Windows desktop voice input tool. Press and hold your shortcut, speak naturally, release it, and the recognized text is inserted into the active application.

- **Local recognition:** audio is processed on your computer by default.
- **Beginner-first setup:** choose a language, download a recommended model, and start speaking.
- **Automatic hardware choice:** CPU is the fallback; compatible NVIDIA CUDA hardware can use an optional GPU runtime.
- **Native desktop app:** the release build opens as a Tauri window and can stay in the system tray. The browser port is for development only.
- **File transcription:** audio and video transcription is available when the optional FFmpeg component is installed.

## Current preview

![VoiceType current interface preview](voicetype-validation.png)

This image shows the current development interface. It is included to show the product direction; it is not a promise that every item shown has passed clean-machine release acceptance.

## Try it

**Project page:** [github.com/leo-cheung-itlger/voice-type](https://github.com/leo-cheung-itlger/voice-type)

The public repository currently contains source code and development instructions. A tested, standalone installer is not published yet. If you do not normally install Python or developer tools, please wait for the first ready-to-run Windows package instead of downloading the source ZIP.

1. Use Windows x64 with Python 3.12, Node.js, and npm.
2. Create the CPU development environment using the commands in [RUNBOOK.md](RUNBOOK.md).
3. Start the development UI, open the local page, and download a model from **Settings → Recognition**.
4. Keep the default language as **Mandarin** unless you have a reason to change it.
5. Hold the configured shortcut, speak, and release it to insert the result.

The production desktop build is launched with `VoiceType.exe`. `start-live-ui.ps1` and `http://127.0.0.1:55343` are development-only entry points.

## Models and hardware

| Computer | Recommended model | Runtime |
| --- | --- | --- |
| No NVIDIA GPU, AMD/Intel GPU, or CUDA unavailable | SenseVoice INT8 | CPU |
| Compatible NVIDIA CUDA available | Qwen3-ASR 0.6B | Optional CUDA runtime |
| Higher recognition quality | Qwen3-ASR 1.7B | Manual choice; higher memory use |
| File transcription on a small CPU machine | Paraformer Chinese | CPU; language constraint is limited |

The default mode is **Automatic**. If a GPU component or GPU model fails to load, VoiceType reports the reason and can fall back to an installed SenseVoice CPU model. GPU components are downloaded only after the user confirms.

Model downloads use a verified ModelScope file manifest first when available, then fall back to the official Hugging Face source. Files are checked with SHA-256. GGUF, Vulkan, and FunASR Nano backends remain disabled because their runtime is not implemented yet.

Supported recognition language choices currently include Mandarin, automatic detection, English, Cantonese, Japanese, and Korean. This setting controls recognition; it is not a translation feature.

## Privacy

- Default speech recognition stays on the local machine.
- Model downloads need network access to the listed model sources.
- Optional AI polishing in file transcription sends text only to the service configured by the user.
- Portable data, downloaded models, recordings, and logs stay in the application's data directories.

## Known limits

- AMD/Intel GPU acceleration is not supported yet.
- Low-end physical hardware and clean Windows 10/11 machines still need dedicated acceptance testing.
- The repository does not currently publish a guaranteed minimum RAM or VRAM requirement.
- The source tree is public, but the project license has not been selected yet. Public visibility does not grant redistribution rights.

## Build from source

<details>
<summary>Developer setup</summary>

Requirements: Windows x64, Python 3.12, Node.js/npm, Rust and MSVC Build Tools for the Tauri shell. The optional Windows capture helper is built separately with .NET SDK; end users do not need the SDK.

```powershell
python -m venv venv
.\venv\Scripts\python.exe -m pip install --require-hashes -r requirements-cpu.lock
cd frontend
npm ci
cd ..
.\scripts\start-dev.ps1
```

For Qwen CUDA development, install the separately locked CUDA environment:

```powershell
.\venv\Scripts\python.exe -m pip install --require-hashes -r requirements-cuda.lock --extra-index-url https://download.pytorch.org/whl/cu128
```

The CPU runtime does not include PyTorch. SciPy is kept in `requirements-dev.txt` for microphone diagnostics only. FFmpeg is optional; include it in a portable build with:

```powershell
python scripts/build_portable.py --include-ffmpeg --exe path\to\VoiceType.exe
```

See [RUNBOOK.md](RUNBOOK.md) for validation and packaging details.

</details>

## Documentation

- [中文说明](README.zh-CN.md)
- [Project status and acceptance limits](PROJECT_STATUS.md)
- [Build and validation runbook](RUNBOOK.md)
- [Third-party components and licenses](THIRD_PARTY.md)

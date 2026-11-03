# ADR 0004: Desktop Packaging Strategy

## Status

Accepted; updated 2026-11-03 for public portable release.

## Context

The Vue / Tauri / Python architecture works, but a portable EXE that depends on a development venv is not an independent distribution. CPU users should not download the complete CUDA environment.

## Decision

1. Target Windows 10/11 x64 portable alpha first. Keep the existing application architecture.
2. Bundle isolated CPython 3.12 x64 and hash-locked CPU dependencies. Disable site/user-site lookup; resolve files relative to the release root marked by portable.json.
3. Distribute the locked CUDA/Qwen runtime as an optional version-matched, checksummed component. Split assets to respect the hosting size limit. Do not install packages at user startup.
4. Download compatible model weights only after an explicit user action; support existing-model import. Keep models separate from the base archive.
5. Store data, logs and downloaded models inside the portable directory. Imported paths remain external and are shown explicitly.
6. Publish the Windows capture helper as self-contained; fall back to basic recording when unavailable. Provide official WebView2 installation guidance.
7. Closing the window hides it to tray; tray Quit exits the runtime. A formal installer, other operating systems and AMD/Intel GPU acceleration remain deferred.
8. The maintainer explicitly approved public release after the available cloud Windows build and local isolated-runtime acceptance, with untested systems/hardware disclosed in release notes (2026-11-03). Clean Windows 10/11, physical low-end and driver-failure coverage remain unverified and must not be claimed. Third-party redistribution materials remain required.
9. Ship one CPU base archive without models or FFmpeg. First launch offers SenseVoice; NVIDIA users review exact component size plus estimated model size, confirm download, and enable Qwen only after validation. Source uses MIT. Build CPU/CUDA independently on GitHub Actions; remove local temporary release files only after public downloads are verified.

## Consequences

- End users do not need system Python, a development checkout or .NET SDK.
- The optional CUDA component remains large because it includes upstream Qwen runtime dependencies; the CPU base avoids this cost.
- Clean-host testing must cover non-ASCII and space-containing paths, recording fallback, hotkey output and restart/quit lifecycle.
- Runtime dependencies, model downloads and FFmpeg have separate license obligations; source publication does not imply a binary release is ready.

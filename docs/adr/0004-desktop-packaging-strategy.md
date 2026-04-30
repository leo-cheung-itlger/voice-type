# ADR 0004: Desktop Packaging Strategy

## Status

Accepted

## Context

VoiceType currently has a working Vue control console and Python runtime. The user wants a real desktop window with tray minimize, tray quit, and eventual EXE packaging. The runtime still depends on external model files, a Python virtual environment, local ffmpeg, and GPU-specific model performance decisions.

## Decision

Use Tauri as the desktop shell, but stage packaging:

1. Build a Tauri development shell first.
2. Ship a portable Windows alpha before a formal installer.
3. Keep models outside the application bundle for now.
4. Use tray Quit as the only full-exit path; the window close button hides to tray.
5. Defer macOS packages until the Windows lifecycle is stable and a macOS build host is available.

## Rationale

A portable alpha is safer while runtime behavior is still changing. It avoids registry/start-menu/update complexity and makes it easy to inspect logs and replace models. A formal installer is useful later for shortcuts, auto-start, upgrades, and bundled runtime management, but it should not be the first package while ASR process lifecycle and model recommendations are still being tuned.

## Consequences

- The first desktop package may require being run from the project/runtime folder.
- The Python `venv`, model directories, and ffmpeg remain external until a later packaging phase.
- The Tauri shell can validate real window/tray behavior before installer work starts.

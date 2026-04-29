# ADR 0003: File Transcription API First

## Status

Accepted on 2026-04-29.

## Context

VoiceType needs audio/video file transcription, subtitle export, and optional LLM polishing without destabilizing the real-time shortcut dictation path. Browser file inputs cannot reliably expose original local file paths, while a later Tauri shell can pass those paths directly.

## Decision

Implement file transcription as an independent API-managed queue:

- The real-time ASR server/client remains separate.
- `POST /api/transcriptions` accepts local absolute file paths for desktop/Tauri/agent use.
- `POST /api/transcriptions/upload` accepts browser uploads and stores them under ignored local runtime data.
- Results are normalized to JSON first, with TXT and SRT generated from that structure.
- SRT uses approximate chunk timestamps until a timestamp-capable ASR backend is added.
- LLM polishing is limited to file transcription outputs and uses a local ignored OpenAI-compatible configuration.
- Agent integration starts with HTTP API plus a project-local Skill instruction file; MCP can wrap the same API later.

## Consequences

- Current browser users can drag or select files, but output defaults to the upload cache because browsers hide the source path.
- Tauri can later reuse the same API and restore "output beside source file" for drag/drop.
- Long file transcription can be slower than real-time dictation and is serialized to avoid loading multiple ASR models at once.

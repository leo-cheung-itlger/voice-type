---
name: voicetype-transcription
description: Use when an agent needs to call a local VoiceType instance to transcribe audio or video files into JSON, TXT, or SRT, optionally with OpenAI-compatible LLM polishing. Triggers include VoiceType transcription, local subtitle export, audio/video to text, and subtitle polishing through the VoiceType HTTP API.
---

# VoiceType Transcription

Use the local VoiceType API instead of re-implementing ASR in the agent.

## Preconditions

- VoiceType API is running at `http://127.0.0.1:52342`.
- `GET /api/ffmpeg/status` returns `available: true`.
- Input files are local paths visible to the VoiceType machine, or are uploaded through `/api/transcriptions/upload`.
- LLM polishing requires `GET /api/llm/config` to show a configured `model` and saved API key.

## Workflow

1. Check runtime:

```bash
curl http://127.0.0.1:52342/api/ffmpeg/status
curl http://127.0.0.1:52342/api/models
```

2. Create a path-based task:

```bash
curl -X POST http://127.0.0.1:52342/api/transcriptions ^
  -H "Content-Type: application/json" ^
  -d "{\"input_files\":[\"C:\\\\Media\\\\demo.mp4\"],\"formats\":[\"json\",\"txt\",\"srt\"],\"polish\":false}"
```

3. Poll until `status` is `completed`, `failed`, or `cancelled`:

```bash
curl http://127.0.0.1:52342/api/transcriptions/<task_id>
```

4. Read output paths:

```bash
curl http://127.0.0.1:52342/api/transcriptions/<task_id>/outputs
```

## LLM Polishing

Use polishing only for file transcription, not real-time dictation.

Configure:

```bash
curl -X PUT http://127.0.0.1:52342/api/llm/config ^
  -H "Content-Type: application/json" ^
  -d "{\"base_url\":\"https://api.openai.com/v1\",\"model\":\"gpt-4.1-mini\",\"api_key\":\"...\",\"temperature\":0.2}"
```

Create with one of these modes:

- `correct`: fix recognition mistakes only.
- `deoralize`: remove filler words and repeated oral fragments.
- `formal`: rewrite into clearer written style.

Example:

```bash
curl -X POST http://127.0.0.1:52342/api/transcriptions ^
  -H "Content-Type: application/json" ^
  -d "{\"input_files\":[\"C:\\\\Media\\\\demo.mp3\"],\"formats\":[\"txt\",\"srt\",\"json\"],\"polish\":true,\"polish_mode\":\"deoralize\"}"
```

## Notes

- SRT timestamps are approximate fixed-window timestamps unless the selected ASR model later provides native timestamps.
- If a task fails, inspect `error` on the task and each file row.
- Use `POST /api/transcriptions/<task_id>/cancel` to cancel queued or running work.

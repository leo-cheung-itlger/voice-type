"""File transcription uses the same resident ASR service as hotkey input."""
import json
import uuid
from websockets.sync.client import connect


class RemoteASREngine:
    def __init__(self, port, state):
        self.port = port
        self.model_name = state["active_model"]
        self.backend = state.get("acceleration", "")
        self.language = state.get("effective_language", state.get("active_language", "auto"))

    def recognize(self, audio, sample_rate=16000):
        with connect(f"ws://127.0.0.1:{self.port}", max_size=4 * 1024 * 1024, open_timeout=10) as ws:
            ws.send(json.dumps({"type": "audio_start", "task_id": str(uuid.uuid4()), "source": "transcription", "sample_rate": sample_rate}))
            ws.send(audio)
            ws.send(json.dumps({"type": "audio_end", "sample_rate": sample_rate}))
            while True:
                result = json.loads(ws.recv(timeout=300))
                self.last_result = result
                if result.get("error"):
                    raise RuntimeError(result["error"])
                if result.get("is_final"):
                    return result.get("text", "")

from dataclasses import dataclass, field
from typing import Literal
import os

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
MODELS_DIR = os.path.join(os.path.dirname(BASE_DIR), "models")
DATA_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "data")
LOGS_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "logs")


@dataclass
class ServerConfig:
    host: str = "0.0.0.0"
    port: int = 52341
    model: Literal["qwen3-asr-0.6b", "qwen3-asr-1.7b", "funasr-nano", "sensevoice", "paraformer"] = "qwen3-asr-1.7b"
    model_dir: str = ""
    gpu: bool = True
    gpu_backend: Literal["vulkan", "dml", "cuda"] = "cuda"
    max_connections: int = 10
    ping_interval: int = 20
    ping_timeout: int = 10

    def __post_init__(self):
        if not self.model_dir:
            model_map = {
                "qwen3-asr-0.6b": "Qwen3-ASR-0.6B",
                "qwen3-asr-1.7b": "Qwen3-ASR-1.7B",
                "funasr-nano": "Fun-ASR-Nano-GGUF",
                "sensevoice": "SenseVoice-Small",
                "paraformer": "paraformer-offline-zh",
            }
            self.model_dir = os.path.join(MODELS_DIR, model_map.get(self.model, ""))


@dataclass
class ClientConfig:
    server_host: str = "127.0.0.1"
    server_port: int = 52341
    shortcut_key: str = "caps_lock"
    mouse_button: int = 2
    sample_rate: int = 48000
    channels: int = 1
    output_mode: Literal["clipboard", "keyboard", "hybrid"] = "clipboard"
    restore_clipboard: bool = True
    paste_delay: float = 0.05
    restore_delay: float = 0.2
    type_delay: float = 0.01
    clipboard_verify: bool = True
    clipboard_verify_timeout: float = 0.5
    clipboard_verify_interval: float = 0.02
    save_audio: bool = True
    audio_dir: str = ""
    hotword_files: list = field(default_factory=lambda: ["hot-zh.txt", "hot-en.txt", "hot-rule.txt"])
    reconnect_max_retries: int = 0
    reconnect_base_delay: float = 1.0
    reconnect_max_delay: float = 30.0
    heartbeat_interval: int = 15

    def __post_init__(self):
        if not self.audio_dir:
            self.audio_dir = os.path.join(DATA_DIR, "recordings")


@dataclass
class APIConfig:
    host: str = "127.0.0.1"
    port: int = 52342
    cors_origins: list = field(default_factory=lambda: ["*"])


@dataclass
class AppConfig:
    server: ServerConfig = field(default_factory=ServerConfig)
    client: ClientConfig = field(default_factory=ClientConfig)
    api: APIConfig = field(default_factory=APIConfig)

from dataclasses import asdict, dataclass, field, fields, is_dataclass
from typing import Any, Dict, Literal
import json
import os

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DEFAULT_ASR_PORT = 55341
DEFAULT_API_PORT = 55342
DEFAULT_FRONTEND_PORT = 55343
LEGACY_ASR_PORT = 52341
LEGACY_API_PORT = 52342
DEFAULT_MODELS_DIR = os.path.join(os.path.dirname(BASE_DIR), "models")
LEGACY_MODELS_DIR = r"C:\Program Files\CapsWriter-Offline-Windows-64bit\models"
MODELS_DIR = os.environ.get("VOICETYPE_MODELS_DIR", DEFAULT_MODELS_DIR)
DATA_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "data")
LOGS_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "logs")
APP_CONFIG_FILE = os.path.join(DATA_DIR, "app_config.json")

MODEL_DIR_NAMES = {
    "qwen3-asr-0.6b": "Qwen3-ASR-0.6B",
    "qwen3-asr-1.7b": "Qwen3-ASR-1.7B",
    "qwen3-asr-1.7b-gguf-vulkan": "Qwen3-ASR-1.7B-GGUF",
    "funasr-nano": "Fun-ASR-Nano-GGUF",
    "sensevoice": "SenseVoice-Small",
    "paraformer": "paraformer-offline-zh",
}


def model_root_candidates() -> list:
    roots = []
    for root in (
        os.environ.get("VOICETYPE_MODELS_DIR", ""),
        DEFAULT_MODELS_DIR,
        os.path.join(BASE_DIR, "models"),
        LEGACY_MODELS_DIR,
    ):
        if root and root not in roots:
            roots.append(root)
    return roots


def resolve_model_dir(model: str) -> str:
    dirname = MODEL_DIR_NAMES.get(model, "")
    if not dirname:
        return ""

    first_candidate = os.path.join(MODELS_DIR, dirname)
    for root in model_root_candidates():
        candidate = os.path.join(root, dirname)
        if os.path.isdir(candidate):
            return candidate
    return first_candidate


@dataclass
class ServerConfig:
    host: str = "0.0.0.0"
    port: int = DEFAULT_ASR_PORT
    model: Literal["qwen3-asr-0.6b", "qwen3-asr-1.7b", "qwen3-asr-1.7b-gguf-vulkan", "funasr-nano", "sensevoice", "paraformer"] = "qwen3-asr-1.7b"
    model_dir: str = ""
    gpu: bool = True
    gpu_required: bool = True
    allow_cpu_fallback: bool = False
    gpu_backend: Literal["vulkan", "dml", "cuda"] = "cuda"
    max_connections: int = 10
    ping_interval: int = 20
    ping_timeout: int = 10

    def __post_init__(self):
        if not self.model_dir or not os.path.isdir(self.model_dir):
            self.model_dir = resolve_model_dir(self.model)


@dataclass
class ClientConfig:
    server_host: str = "127.0.0.1"
    server_port: int = DEFAULT_ASR_PORT
    shortcut_key: str = "caps_lock"
    mouse_button: int = 2
    sample_rate: int = 48000
    channels: int = 1
    input_device_index: int = -1
    input_device_name: str = ""
    input_device_host_api: str = ""
    input_device_sample_rate: int = 0
    auto_gain_enabled: bool = True
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
    archive_root: str = ""
    min_press_seconds: float = 0.1
    hotword_files: list = field(default_factory=lambda: ["hot-zh.txt", "hot-en.txt", "hot-rule.txt"])
    notification_enabled: bool = True
    notification_sound: bool = True
    reconnect_max_retries: int = 0
    reconnect_base_delay: float = 1.0
    reconnect_max_delay: float = 30.0
    heartbeat_interval: int = 15

    def __post_init__(self):
        if not self.audio_dir:
            self.audio_dir = os.path.join(DATA_DIR, "recordings")
        if not self.archive_root:
            self.archive_root = os.path.join(DATA_DIR, "archive")


@dataclass
class APIConfig:
    host: str = "127.0.0.1"
    port: int = DEFAULT_API_PORT
    cors_origins: list = field(default_factory=lambda: ["*"])


@dataclass
class AppConfig:
    server: ServerConfig = field(default_factory=ServerConfig)
    client: ClientConfig = field(default_factory=ClientConfig)
    api: APIConfig = field(default_factory=APIConfig)


def _known_fields(cls) -> set:
    return {f.name for f in fields(cls)}


def _merge_dataclass(instance: Any, values: Dict[str, Any]):
    if not isinstance(values, dict):
        return instance
    allowed = _known_fields(type(instance))
    for key, value in values.items():
        if key in allowed:
            setattr(instance, key, value)
    if hasattr(instance, "__post_init__"):
        instance.__post_init__()
    return instance


def app_config_to_dict(config: AppConfig) -> Dict[str, Any]:
    if not is_dataclass(config):
        return {}
    return asdict(config)


def load_app_config(filepath: str = APP_CONFIG_FILE) -> AppConfig:
    config = AppConfig()
    if not os.path.exists(filepath):
        return config

    try:
        with open(filepath, "r", encoding="utf-8") as f:
            data = json.load(f)
    except Exception:
        return config

    _merge_dataclass(config.server, data.get("server", {}))
    _merge_dataclass(config.client, data.get("client", {}))
    _merge_dataclass(config.api, data.get("api", {}))
    _migrate_legacy_ports(config)
    return config


def _migrate_legacy_ports(config: AppConfig):
    if config.server.port == LEGACY_ASR_PORT:
        config.server.port = DEFAULT_ASR_PORT
    if config.client.server_port == LEGACY_ASR_PORT:
        config.client.server_port = DEFAULT_ASR_PORT
    if config.api.port == LEGACY_API_PORT:
        config.api.port = DEFAULT_API_PORT


def save_app_config(config: AppConfig, filepath: str = APP_CONFIG_FILE):
    os.makedirs(os.path.dirname(filepath), exist_ok=True)
    with open(filepath, "w", encoding="utf-8") as f:
        json.dump(app_config_to_dict(config), f, ensure_ascii=False, indent=2)


def update_app_config(values: Dict[str, Any], filepath: str = APP_CONFIG_FILE) -> AppConfig:
    config = load_app_config(filepath)
    _merge_dataclass(config.server, values.get("server", {}))
    _merge_dataclass(config.client, values.get("client", {}))
    _merge_dataclass(config.api, values.get("api", {}))
    save_app_config(config, filepath)
    return config

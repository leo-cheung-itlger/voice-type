"""Model capabilities and install contracts shared by API, engine and downloader."""
from pathlib import Path

LANGUAGES = {"zh": "普通话", "auto": "自动检测", "en": "英语", "yue": "粤语", "ja": "日语", "ko": "韩语"}
QWEN_LANGUAGES = {"zh": "Chinese", "auto": None, "en": "English", "yue": "Cantonese", "ja": "Japanese", "ko": "Korean"}
# ModelScope is only used for hub models whose repository is mirrored with the
# same file names.  The downloader still verifies every file hash and falls
# back to Hugging Face when the mirror manifest is unavailable.
MODEL_SOURCE_POLICY = ("modelscope", "huggingface")
CATALOG = {
    "sensevoice": {
        "name": "SenseVoice INT8", "directory": "SenseVoice-Small", "backend": "sherpa-onnx",
        "implemented": True, "languages": list(LANGUAGES), "language_hint": True,
        "files": ["model.int8.onnx", "tokens.txt"], "role": "cpu",
        "archive": "sherpa-onnx-sense-voice-zh-en-ja-ko-yue-int8-2024-07-17.tar.bz2",
        "download_bytes": 163002883,
        "sha256": "7d1efa2138a65b0b488df37f8b89e3d91a60676e416f515b952358d83dfd347e",
    },
    "paraformer": {
        "name": "Paraformer 中文", "directory": "paraformer-offline-zh", "backend": "sherpa-onnx",
        "implemented": True, "languages": ["zh", "auto", "en"], "language_hint": False,
        "files": ["model.int8.onnx", "tokens.txt"], "role": "fast",
        "archive": "sherpa-onnx-paraformer-zh-2023-03-28.tar.bz2", "download_bytes": 1035472389,
    },
    "qwen3-asr-0.6b": {
        "name": "Qwen3-ASR 0.6B", "directory": "Qwen3-ASR-0.6B", "backend": "qwen-asr",
        "implemented": True, "languages": list(LANGUAGES), "language_hint": True,
        "files": ["config.json", "model.safetensors"], "role": "daily",
        "hub": "Qwen/Qwen3-ASR-0.6B", "download_bytes": 1300000000,
    },
    "qwen3-asr-1.7b": {
        "name": "Qwen3-ASR 1.7B", "directory": "Qwen3-ASR-1.7B", "backend": "qwen-asr",
        "implemented": True, "languages": list(LANGUAGES), "language_hint": True,
        "files": ["config.json", "model.safetensors"], "role": "quality",
        "hub": "Qwen/Qwen3-ASR-1.7B", "download_bytes": 3500000000,
    },
    "qwen3-asr-1.7b-gguf-vulkan": {
        "name": "Qwen3-ASR GGUF（开发中）", "directory": "Qwen3-ASR-1.7B-GGUF", "backend": "gguf-vulkan",
        "implemented": False, "languages": [], "language_hint": False, "files": [], "role": "experimental",
    },
    "funasr-nano": {
        "name": "FunASR Nano（开发中）", "directory": "Fun-ASR-Nano-GGUF", "backend": "gguf",
        "implemented": False, "languages": [], "language_hint": False, "files": [], "role": "experimental",
    },
}


def validate_model(model: str, language: str = "zh") -> dict:
    spec = CATALOG.get(model)
    if not spec or not spec["implemented"]:
        raise ValueError("该模型后端尚未实现，不能使用或下载")
    if language not in spec["languages"]:
        raise ValueError(f"{spec['name']} 不支持 {LANGUAGES.get(language, language)}，请更换模型或识别语言")
    return spec


def model_installed(model: str, directory: str) -> bool:
    spec = CATALOG.get(model, {})
    required = spec.get("files", [])
    return bool(spec.get("implemented") and required and all((Path(directory) / name).is_file() and (Path(directory) / name).stat().st_size > 0 for name in required))


def model_web_url(model: str) -> str:
    spec = CATALOG[model]
    if not spec["implemented"]:
        return ""
    if spec.get("hub"):
        return f"https://huggingface.co/{spec['hub']}"
    return "https://github.com/k2-fsa/sherpa-onnx/releases/tag/asr-models"


def model_sources(model: str) -> list[dict]:
    """Return safe, non-user-editable source hints for the model catalog."""
    spec = CATALOG[model]
    if not spec.get("implemented"):
        return []
    if spec.get("hub"):
        hub = spec["hub"]
        return [
            {"id": "modelscope", "name": "ModelScope 国内镜像", "base_url": f"https://modelscope.cn/models/{hub}/resolve/master/"},
            {"id": "huggingface", "name": "Hugging Face 官方源", "base_url": f"https://huggingface.co/{hub}/resolve/main/"},
        ]
    return [{"id": "sherpa-onnx", "name": "Sherpa-ONNX 官方源", "base_url": "https://github.com/k2-fsa/sherpa-onnx/releases/download/asr-models/"}]

"""Install the matching optional CUDA runtime from this project's release assets."""
import hashlib
import json
import shutil
import threading
import zipfile
from pathlib import Path
from urllib.request import Request, urlopen

from common.model_download import _download
from config.settings import BASE_DIR, DATA_DIR

REPOSITORY = "https://github.com/leo-cheung-itlger/voice-type"
job = {"status": "idle", "message": "CPU 模型无需此组件", "source": "", "source_attempts": []}
_lock = threading.Lock()


def _run():
    try:
        root = Path(BASE_DIR)
        portable = json.loads((root / "portable.json").read_text(encoding="utf-8"))
        version = portable["version"]
        official_base = f"{REPOSITORY}/releases/download/v{version}/"
        base = official_base
        manifest = None
        manifest_sources = [
            {"id": "official", "name": "GitHub 官方源", "base": official_base},
        ]
        for source in manifest_sources:
            try:
                with urlopen(Request(source["base"] + f"VoiceType-{version}-components.json", headers={"User-Agent": "VoiceType"}), timeout=30) as response:
                    manifest = json.load(response)
                job["source"] = source["name"]
                break
            except Exception as exc:
                job.setdefault("source_attempts", []).append(f"{source['name']}：{exc}")
        if manifest is None:
            raise ValueError("无法读取组件清单：" + "；".join(job.get("source_attempts", [])))
        # A release may publish an exact-hash mirror later.  Only manifest
        # entries are trusted; arbitrary URLs never come from the novice UI.
        sources = manifest.get("sources") or []
        if sources:
            manifest_sources = [{"id": item.get("id", "mirror"), "name": item.get("name", "已验证镜像"), "base": item["base"]} for item in sources if item.get("base")]
            manifest_sources.append({"id": "official", "name": "GitHub 官方源", "base": official_base})
            for source in manifest_sources:
                try:
                    with urlopen(Request(source["base"] + f"VoiceType-{version}-components.json", headers={"User-Agent": "VoiceType"}), timeout=30) as response:
                        candidate = json.load(response)
                    if candidate.get("version") == version and candidate.get("cuda"):
                        manifest = candidate
                        job["source"] = source["name"]
                        base = source["base"]
                        break
                except Exception as exc:
                    job.setdefault("source_attempts", []).append(f"{source['name']}：{exc}")
        if manifest.get("version") != version or not manifest.get("cuda"):
            raise ValueError("本版本尚无通过验收的 GPU 组件，可继续使用 CPU 模型")
        spec = manifest["cuda"]
        cache = Path(DATA_DIR) / "components"
        cache.mkdir(parents=True, exist_ok=True)
        parts = spec.get("parts") or [spec]
        paths = []
        job["total_bytes"] = sum(item["bytes"] for item in parts)
        for item in parts:
            name = item["name"]
            if Path(name).name != name or "/" in name or "\\" in name:
                raise ValueError("无效组件文件名")
            target = cache / name
            _download(base + name, target, job, item["sha256"])
            paths.append(target)
        archive = cache / "runtime-cuda.assembled.zip"
        with archive.open("wb") as output:
            for path in paths:
                with path.open("rb") as source:
                    shutil.copyfileobj(source, output)
        with archive.open("rb") as source:
            if hashlib.file_digest(source, "sha256").hexdigest() != spec["sha256"]:
                raise ValueError("GPU 组件校验失败，请重试")
        if (root / "runtime-cuda").exists():
            raise ValueError("GPU 组件已存在，请关闭应用后移走旧组件再安装")
        staging = cache / ("install-" + version)
        staging.mkdir(exist_ok=True)
        with zipfile.ZipFile(archive) as bundle:
            for item in bundle.infolist():
                relative = Path(item.filename)
                if not relative.parts or relative.parts[0] != "runtime-cuda" or relative.is_absolute() or ".." in relative.parts or ":" in item.filename:
                    raise ValueError("GPU 组件包含无效路径")
                bundle.extract(item, staging)
        if not (staging / "runtime-cuda/python.exe").is_file():
            raise ValueError("GPU 组件缺少专用 Python")
        (staging / "runtime-cuda").rename(root / "runtime-cuda")
        job.update(status="done", message=f"GPU 运行组件已安装，请刷新硬件状态后选择 Qwen 模型（来源：{job.get('source', '官方源')}）")
    except Exception as exc:
        job.update(status="error", error=str(exc), message="组件下载失败，可重试或继续使用 CPU")


def start():
    with _lock:
        if job.get("status") == "running":
            return dict(job)
        if not (Path(BASE_DIR) / "portable.json").is_file():
            raise ValueError("开发环境请使用 requirements-cuda.lock；组件下载仅用于便携版")
        job.update(status="running", message="正在下载 GPU 运行组件", error="", downloaded_bytes=0, completed_bytes=0, source="", source_attempts=[])
        threading.Thread(target=_run, daemon=True).start()
        return dict(job)

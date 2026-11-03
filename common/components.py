"""Install the matching optional CUDA runtime from this project's release assets."""
import hashlib
import json
import shutil
import subprocess
import threading
import zipfile
from pathlib import Path
from urllib.request import Request, urlopen

from common.model_download import _download
from config.settings import BASE_DIR, DATA_DIR

REPOSITORY = "https://github.com/leo-cheung-itlger/voice-type"
job = {"status": "idle", "message": "CPU 模型无需此组件", "source": "", "source_attempts": []}
_lock = threading.Lock()


def plan():
    """Read release metadata only; never download a runtime before consent."""
    portable = json.loads((Path(BASE_DIR) / "portable.json").read_text(encoding="utf-8"))
    version = portable["version"]
    base = f"{REPOSITORY}/releases/download/v{version}/"
    with urlopen(Request(base + f"VoiceType-{version}-components.json", headers={"User-Agent": "VoiceType"}), timeout=30) as response:
        manifest = json.load(response)
    if manifest.get("version") != version or not manifest.get("cuda"):
        raise ValueError("本版本尚无 GPU 组件，可继续使用 CPU 模型")
    spec = manifest["cuda"]
    parts = spec.get("parts") or [spec]
    for item in [spec, *parts]:
        name = item.get("name", "")
        if not name or name in (".", "..") or any(c in name for c in '/\\:'):
            raise ValueError("无效组件文件名")
        if not isinstance(item.get("bytes"), int) or item["bytes"] <= 0:
            raise ValueError("无效组件大小")
        sha = item.get("sha256", "")
        if len(sha) != 64 or any(c not in "0123456789abcdef" for c in sha):
            raise ValueError("无效组件校验值")
    total = sum(item["bytes"] for item in parts)
    if total != spec["bytes"]:
        raise ValueError("组件分卷大小与清单不符")
    return {"version": version, "bytes": total, "sha256": spec["sha256"], "spec": spec, "base": base}


def _run(approved):
    try:
        root = Path(BASE_DIR)
        # Install the exact manifest shown before confirmation.
        version, base, spec = approved["version"], approved["base"], approved["spec"]
        job["source"] = "GitHub 官方源"
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
        result = subprocess.run(
            [str(staging / "runtime-cuda/python.exe"), "-c", "import torch,qwen_asr,sherpa_onnx; assert torch.cuda.is_available(), 'NVIDIA 驱动或 GPU 与组件不兼容'"],
            capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=120,
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
        if result.returncode:
            raise ValueError("GPU 组件验证失败，CPU 配置保持可用：" + result.stderr[-1200:])
        (staging / "runtime-cuda").rename(root / "runtime-cuda")
        # Delete only these verified download files, after successful installation.
        for path in {*paths, archive}:
            path.unlink(missing_ok=True)
        staging.rmdir()
        job.update(status="done", message=f"GPU 运行组件已安装，请刷新硬件状态后选择 Qwen 模型（来源：{job.get('source', '官方源')}）")
    except Exception as exc:
        job.update(status="error", error=str(exc), message="组件下载失败，可重试或继续使用 CPU")


def start(sha256):
    with _lock:
        if job.get("status") == "running":
            return dict(job)
        if not (Path(BASE_DIR) / "portable.json").is_file():
            raise ValueError("开发环境请使用 requirements-cuda.lock；组件下载仅用于便携版")
        approved = plan()
        if approved["sha256"] != sha256:
            raise ValueError("组件清单已变化，请重新查看下载大小并确认")
        if (Path(BASE_DIR) / "runtime-cuda").exists():
            raise ValueError("GPU 组件已存在，请先检查硬件状态")
        job.update(status="running", message="正在下载 GPU 运行组件", error="", downloaded_bytes=0, completed_bytes=0, source="", source_attempts=[])
        threading.Thread(target=_run, args=(approved,), daemon=True).start()
        return dict(job)

"""Explicit, resumable downloads. No package installation on the user's machine."""
import hashlib
import json
import shutil
import tarfile
import threading
import time
from pathlib import Path
from urllib.request import Request, urlopen
from urllib.error import HTTPError

from config.settings import DATA_DIR, MODELS_DIR
from common.model_catalog import CATALOG, model_installed, model_sources, validate_model

jobs = {}
_lock = threading.Lock()


def _download(url, destination, job, expected_sha=""):
    destination.parent.mkdir(parents=True, exist_ok=True)
    if destination.exists() and expected_sha:
        with destination.open("rb") as existing:
            if hashlib.file_digest(existing, "sha256").hexdigest() == expected_sha:
                job["completed_bytes"] = job.get("completed_bytes", 0) + destination.stat().st_size
                job["downloaded_bytes"] = job["completed_bytes"]
                return
    partial = destination.with_name(destination.name + ".partial")
    offset = partial.stat().st_size if partial.exists() else 0
    headers = {"User-Agent": "VoiceType/1.0"}
    if offset:
        headers["Range"] = f"bytes={offset}-"
    try:
        response = urlopen(Request(url, headers=headers), timeout=60)
    except HTTPError as exc:
        if exc.code == 416 and offset:
            # A previous attempt may have received the whole file before it stopped.
            if expected_sha:
                with partial.open("rb") as existing:
                    valid = hashlib.file_digest(existing, "sha256").hexdigest() == expected_sha
                if valid:
                    partial.replace(destination)
                    job["completed_bytes"] = job.get("completed_bytes", 0) + destination.stat().st_size
                    job["downloaded_bytes"] = job["completed_bytes"]
                    return
            partial.unlink()
            return _download(url, destination, job, expected_sha)
        raise
    with response:
        append = offset > 0 and response.status == 206
        if not append:
            offset = 0
        base = job.get("completed_bytes", 0)
        with partial.open("ab" if append else "wb") as output:
            received = offset
            while chunk := response.read(1024 * 1024):
                output.write(chunk)
                received += len(chunk)
                job["downloaded_bytes"] = base + received
        length = int(response.headers.get("Content-Length", 0))
        if length and received - offset != length:
            raise RuntimeError("下载中断，请重试以继续下载")
    if expected_sha:
        digest = hashlib.sha256()
        with partial.open("rb") as handle:
            while chunk := handle.read(1024 * 1024):
                digest.update(chunk)
        if digest.hexdigest() != expected_sha:
            partial.unlink()
            raise RuntimeError("下载校验失败，请重试")
    partial.replace(destination)
    job["completed_bytes"] = base + destination.stat().st_size


def _json_get(url):
    with urlopen(Request(url, headers={"User-Agent": "VoiceType/1.0"}), timeout=30) as response:
        return json.load(response)


def _hub_files(spec, job):
    """Resolve a hub model from domestic mirror first, then official source."""
    hub = spec["hub"]
    attempts = []
    # ModelScope exposes SHA-256 values in its repository manifest.  This is
    # deliberately discovered at download time; we never invent a mirror URL.
    try:
        payload = _json_get(f"https://modelscope.cn/api/v1/models/{hub}/repo/files?Revision=master&Recursive=true")
        rows = ((payload.get("Data") or {}).get("Files") or [])
        files = [row for row in rows if "/" not in row.get("Path", row.get("Name", "")) and row.get("Name", "").endswith((".json", ".safetensors", ".txt", ".tiktoken"))]
        names = {row.get("Name") for row in files}
        if files and all(name in names for name in spec["files"]):
            job["source"] = "ModelScope 国内镜像"
            job["source_id"] = "modelscope"
            return [{"name": row["Name"], "size": row.get("Size", 0), "sha256": row.get("Sha256", ""), "url": f"https://modelscope.cn/models/{hub}/resolve/master/{row['Path']}"} for row in files]
        attempts.append("ModelScope 文件清单不完整")
    except Exception as exc:
        attempts.append(f"ModelScope：{exc}")

    try:
        manifest = _json_get(f"https://huggingface.co/api/models/{hub}?blobs=true")
        revision = manifest["sha"]
        files = [row for row in manifest["siblings"] if "/" not in row["rfilename"] and row["rfilename"].endswith((".json", ".safetensors", ".txt", ".tiktoken"))]
        job["source"] = "Hugging Face 官方源"
        job["source_id"] = "huggingface"
        return [{"name": row["rfilename"], "size": row.get("size", row.get("lfs", {}).get("size", 0)), "sha256": row.get("lfs", {}).get("sha256", ""), "url": f"https://huggingface.co/{hub}/resolve/{revision}/{row['rfilename']}"} for row in files]
    except Exception as exc:
        attempts.append(f"Hugging Face：{exc}")
        raise RuntimeError("；".join(attempts)) from exc


def _run(model, job):
    spec = CATALOG[model]
    target = Path(job["target_dir"])
    cache = Path(MODELS_DIR) / ".downloads" / model
    try:
        target.mkdir(parents=True, exist_ok=True)
        if spec.get("archive"):
            archive = cache / spec["archive"]
            job["message"] = "正在下载 Sherpa-ONNX 官方模型"
            job["source"] = "Sherpa-ONNX 官方源"
            _download("https://github.com/k2-fsa/sherpa-onnx/releases/download/asr-models/" + spec["archive"], archive, job, spec.get("sha256", ""))
            job["message"] = "正在安装并验证模型文件"
            with tarfile.open(archive, "r:bz2") as bundle:
                for member in bundle:
                    name = Path(member.name).name
                    if not member.isfile() or name not in spec["files"]:
                        continue
                    source = bundle.extractfile(member)
                    with (target / (name + ".installing")).open("wb") as output:
                        shutil.copyfileobj(source, output)
                    (target / (name + ".installing")).replace(target / name)
        else:
            files = _hub_files(spec, job)
            job["total_bytes"] = sum(row.get("size", 0) for row in files)
            for row in files:
                name = row["name"]
                job["message"] = f"正在下载 {name}"
                _download(row["url"], target / name, job, row.get("sha256", ""))
        if not model_installed(model, str(target)):
            raise RuntimeError("模型文件不完整，请重试下载或导入正确的模型目录")
        job.update(status="done", message=f"模型已安装，可选择并应用（来源：{job.get('source', '官方源')}）", progress=100)
    except Exception as error:
        job.update(status="error", error=str(error), message=f"下载失败（已尝试：{job.get('source', '国内镜像、官方源')}），点击重试可继续下载")
    finally:
        job["finished_at"] = time.time()


def start_download(model):
    spec = validate_model(model)
    with _lock:
        if jobs.get(model, {}).get("status") == "running":
            return dict(jobs[model])
        job = {"model": model, "status": "running", "target_dir": str(Path(MODELS_DIR) / spec["directory"]), "started_at": time.time(), "message": "准备下载（优先检查国内镜像）", "error": "", "downloaded_bytes": 0, "completed_bytes": 0, "total_bytes": spec["download_bytes"], "source": "", "source_id": "", "source_policy": list(model_sources(model))}
        jobs[model] = job
        threading.Thread(target=_run, args=(model, job), daemon=True).start()
        return dict(job)


def import_model(model, directory):
    validate_model(model)
    path = Path(directory).expanduser().resolve()
    if not model_installed(model, str(path)):
        raise ValueError("该目录缺少模型所需文件，或模型格式与识别引擎不匹配")
    locations_path = Path(DATA_DIR) / "model_locations.json"
    with _lock:
        locations_path.parent.mkdir(parents=True, exist_ok=True)
        locations = json.loads(locations_path.read_text(encoding="utf-8")) if locations_path.exists() else {}
        locations[model] = str(path)
        temporary = locations_path.with_suffix(".tmp")
        temporary.write_text(json.dumps(locations, ensure_ascii=False), encoding="utf-8")
        temporary.replace(locations_path)
    return {"model": model, "path": str(path), "installed": True}

import importlib.util
import json
import os
import subprocess
import sys
from pathlib import Path

from config.settings import BASE_DIR, DATA_DIR


def write_runtime_state(**values):
    import psutil
    state = {"pid": os.getpid(), "created": psutil.Process().create_time(), **values}
    target = Path(DATA_DIR) / "asr_runtime.json"
    target.parent.mkdir(parents=True, exist_ok=True)
    temporary = target.with_suffix(".tmp")
    temporary.write_text(json.dumps(state, ensure_ascii=False), encoding="utf-8")
    temporary.replace(target)


def runtime_state():
    import psutil
    try:
        state = json.loads((Path(DATA_DIR) / "asr_runtime.json").read_text(encoding="utf-8"))
        process = psutil.Process(state["pid"])
        if abs(process.create_time() - state["created"]) < 1:
            return state
    except (OSError, ValueError, KeyError, psutil.Error):
        pass
    return {"loaded": False, "active_model": "", "active_language": "", "actual_device": "", "error": locals().get("state", {}).get("error", "")}


def python_for_model(model=""):
    if model.startswith("qwen3-asr"):
        addon = Path(BASE_DIR) / "runtime-cuda" / "python.exe"
        if addon.is_file():
            return str(addon)
    bundled = Path(BASE_DIR) / "runtime" / "python.exe"
    if bundled.is_file():
        return str(bundled)
    dev = Path(BASE_DIR) / "venv" / "Scripts" / "python.exe"
    return str(dev) if dev.is_file() else sys.executable


def cuda_status():
    python = python_for_model("qwen3-asr-0.6b")
    if python == sys.executable and importlib.util.find_spec("torch") is None:
        return {"available": False, "cuda_available": False, "version": "", "cuda_version": None, "error": "未安装可选 GPU 运行组件"}
    code = "import json,torch,importlib.util; print(json.dumps(dict(available=True,qwen_available=importlib.util.find_spec('qwen_asr') is not None,version=torch.__version__,cuda_available=torch.cuda.is_available(),cuda_version=torch.version.cuda,error='')))"
    try:
        result = subprocess.run([python, "-c", code], capture_output=True, text=True, encoding="utf-8", timeout=30, creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
        return json.loads(result.stdout.strip().splitlines()[-1])
    except Exception:
        return {"available": False, "cuda_available": False, "version": "", "cuda_version": None, "error": "GPU 运行组件不可用，可使用 CPU 模型"}

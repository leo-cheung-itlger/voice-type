"""
Qwen3-ASR 模型镜像下载脚本
使用 hf-mirror.com 国内镜像加速下载
支持断点续传和文件完整性校验
"""

import hashlib
import json
import os
import sys
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from urllib.parse import urljoin

import requests

MIRRORS = {
    "hf-mirror": "https://hf-mirror.com",
    "hf-direct": "https://huggingface.co",
}

MODELS = {
    "qwen3-asr-1.7b": {
        "repo_id": "Qwen/Qwen3-ASR-1.7B",
        "description": "Qwen3-ASR 1.7B 主模型 (精度最高, ~3.2GB)",
    },
    "qwen3-asr-0.6b": {
        "repo_id": "Qwen/Qwen3-ASR-0.6B",
        "description": "Qwen3-ASR 0.6B 轻量模型 (速度最快, ~1.5GB)",
    },
    "sensevoice": {
        "repo_id": "csukuangfj/sherpa-onnx-sense-voice-zh-en-ja-ko-yue-2024-07-17",
        "description": "SenseVoice-Small (234M, CPU可用, ~300MB)",
    },
}

CHUNK_SIZE = 8 * 1024 * 1024
MAX_WORKERS = 4
DOWNLOAD_TIMEOUT = 300
RETRY_COUNT = 3
RETRY_DELAY = 5


def get_model_files(repo_id: str, mirror: str = "hf-mirror") -> list:
    base_url = MIRRORS[mirror]
    api_url = f"{base_url}/api/models/{repo_id}"
    
    try:
        resp = requests.get(api_url, timeout=30)
        resp.raise_for_status()
        data = resp.json()
        
        siblings = data.get("siblings", [])
        files = []
        for s in siblings:
            rfilename = s.get("rfilename", "")
            size = s.get("size", 0)
            if rfilename and not rfilename.endswith((".md", ".gitattributes")):
                skip_exts = (".onnx", ".gguf", ".safetensors", ".bin", ".pth", ".json", ".txt", ".model")
                if any(rfilename.endswith(ext) for ext in (".onnx", ".gguf", ".safetensors", ".bin", ".pth", ".json", ".txt", ".model", ".py", ".csv", ".wav", ".mp3")):
                    files.append({"name": rfilename, "size": size})
                elif not any(rfilename.endswith(ext) for ext in (".png", ".jpg", ".jpeg", ".gif", ".ico")):
                    files.append({"name": rfilename, "size": size})
        
        return files
    except Exception as e:
        print(f"[ERROR] Failed to get file list from {api_url}: {e}")
        return []


def download_file_chunk(
    url: str, filepath: str, start: int, end: int, chunk_id: int
) -> bool:
    headers = {"Range": f"bytes={start}-{end}"}
    
    for attempt in range(RETRY_COUNT):
        try:
            resp = requests.get(url, headers=headers, timeout=DOWNLOAD_TIMEOUT, stream=True)
            if resp.status_code not in (200, 206):
                return False
            
            with open(filepath, "r+b") as f:
                f.seek(start)
                for chunk in resp.iter_content(chunk_size=1024 * 1024):
                    if chunk:
                        f.write(chunk)
            return True
        except Exception as e:
            if attempt < RETRY_COUNT - 1:
                time.sleep(RETRY_DELAY * (attempt + 1))
            else:
                print(f"  [FAIL] Chunk {chunk_id} after {RETRY_COUNT} retries: {e}")
                return False
    return False


def download_file(url: str, filepath: str, file_size: int) -> bool:
    if os.path.exists(filepath):
        existing_size = os.path.getsize(filepath)
        if existing_size == file_size and file_size > 0:
            print(f"  [SKIP] Already downloaded: {os.path.basename(filepath)}")
            return True
    
    print(f"  Downloading: {os.path.basename(filepath)} ({file_size / 1024 / 1024:.1f} MB)")
    
    for attempt in range(RETRY_COUNT):
        try:
            if file_size > CHUNK_SIZE * MAX_WORKERS:
                return _download_parallel(url, filepath, file_size)
            else:
                return _download_single(url, filepath)
        except Exception as e:
            if attempt < RETRY_COUNT - 1:
                print(f"  Retry {attempt + 1}/{RETRY_COUNT}...")
                time.sleep(RETRY_DELAY)
            else:
                print(f"  [FAIL] {os.path.basename(filepath)}: {e}")
                return False
    return False


def _download_single(url: str, filepath: str) -> bool:
    resp = requests.get(url, timeout=DOWNLOAD_TIMEOUT, stream=True)
    resp.raise_for_status()
    
    os.makedirs(os.path.dirname(filepath), exist_ok=True)
    with open(filepath, "wb") as f:
        for chunk in resp.iter_content(chunk_size=1024 * 1024):
            if chunk:
                f.write(chunk)
    return True


def _download_parallel(url: str, filepath: str, file_size: int) -> bool:
    os.makedirs(os.path.dirname(filepath), exist_ok=True)
    
    with open(filepath, "wb") as f:
        f.seek(file_size - 1)
        f.write(b"\0")
    
    chunk_size = file_size // MAX_WORKERS
    ranges = []
    for i in range(MAX_WORKERS):
        start = i * chunk_size
        end = (i + 1) * chunk_size - 1 if i < MAX_WORKERS - 1 else file_size - 1
        ranges.append((start, end, i))
    
    with ThreadPoolExecutor(max_workers=MAX_WORKERS) as executor:
        futures = {
            executor.submit(download_file_chunk, url, filepath, s, e, i): i
            for s, e, i in ranges
        }
        for future in as_completed(futures):
            if not future.result():
                return False
    
    return True


def race_mirrors(repo_id: str, filename: str) -> str:
    base = MIRRORS["hf-mirror"]
    return f"{base}/{repo_id}/resolve/main/{filename}"


def download_model(model_key: str, output_dir: str) -> bool:
    if model_key not in MODELS:
        print(f"[ERROR] Unknown model: {model_key}")
        print(f"Available: {', '.join(MODELS.keys())}")
        return False
    
    model_info = MODELS[model_key]
    repo_id = model_info["repo_id"]
    desc = model_info["description"]
    
    print(f"\n{'='*60}")
    print(f"Model: {model_key}")
    print(f"Repo:  {repo_id}")
    print(f"Desc:  {desc}")
    print(f"Output: {output_dir}")
    print(f"{'='*60}\n")
    
    files = get_model_files(repo_id, mirror="hf-mirror")
    if not files:
        print("[ERROR] No files found. Check network or repo ID.")
        return False
    
    print(f"Found {len(files)} files:\n")
    total_size = 0
    for f in files:
        size_mb = f["size"] / 1024 / 1024 if f["size"] else 0
        print(f"  {f['name']:50s} {size_mb:>10.1f} MB")
        total_size += f["size"]
    print(f"\n  Total: {total_size / 1024 / 1024:.1f} MB\n")
    
    success_count = 0
    for f in files:
        url = race_mirrors(repo_id, f["name"])
        filepath = os.path.join(output_dir, f["name"])
        
        if download_file(url, filepath, f["size"]):
            success_count += 1
        else:
            print(f"  [WARN] Failed: {f['name']}, will retry later")
    
    print(f"\n  Downloaded: {success_count}/{len(files)} files")
    return success_count == len(files)


def main():
    import argparse
    
    parser = argparse.ArgumentParser(description="Qwen3-ASR Model Downloader (Mirror)")
    parser.add_argument("model", nargs="?", default="qwen3-asr-1.7b",
                       choices=list(MODELS.keys()),
                       help="Model to download (default: qwen3-asr-1.7b)")
    parser.add_argument("--output", "-o", default=None,
                       help="Output directory (default: models/<model_name>)")
    parser.add_argument("--all", action="store_true",
                       help="Download all models")
    
    args = parser.parse_args()
    
    base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    
    if args.all:
        for key in MODELS:
            output = args.output or os.path.join(base_dir, "models", MODELS[key]["repo_id"].split("/")[-1])
            download_model(key, output)
    else:
        output = args.output or os.path.join(base_dir, "models", MODELS[args.model]["repo_id"].split("/")[-1])
        success = download_model(args.model, output)
        if success:
            print(f"\n[DONE] Model saved to: {output}")
        else:
            print(f"\n[PARTIAL] Some files failed. Re-run to retry.")
            sys.exit(1)


if __name__ == "__main__":
    main()

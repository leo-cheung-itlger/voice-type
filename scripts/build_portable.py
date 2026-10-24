"""Build an application-local runtime. Run with the development CPython 3.12 x64."""
import argparse
import hashlib
import json
import shutil
import subprocess
import sys
import zipfile
from pathlib import Path
from urllib.request import urlretrieve

ROOT = Path(__file__).resolve().parents[1]
PYTHON_URL = "https://www.python.org/ftp/python/3.12.10/python-3.12.10-embed-amd64.zip"
PYTHON_SHA256 = "4acbed6dd1c744b0376e3b1cf57ce906f9dc9e95e68824584c8099a63025a3c3"


def digest(path):
    with path.open("rb") as source:
        return hashlib.file_digest(source, "sha256").hexdigest()


def runtime(folder, cuda=False, installed=False):
    cache = ROOT / "dist/build-cache"
    cache.mkdir(parents=True, exist_ok=True)
    archive = cache / "python-3.12.10-embed-amd64.zip"
    if not archive.exists():
        urlretrieve(PYTHON_URL, archive)
    if digest(archive) != PYTHON_SHA256:
        raise RuntimeError("CPython archive checksum mismatch")
    folder.mkdir(parents=True, exist_ok=False)
    with zipfile.ZipFile(archive) as bundle:
        bundle.extractall(folder)
    packages = folder / "Lib/site-packages"
    lock = ROOT / ("requirements-cuda.lock" if cuda else "requirements-cpu.lock")
    if not lock.exists():
        raise RuntimeError(f"Resolve and review pinned dependencies first: {lock.name}")
    command = [sys.executable, "-m", "pip", "install", "--no-compile", "--target", str(packages), "--require-hashes", "-r", str(lock), "--index-url", "https://pypi.org/simple"]
    if cuda:
        command.extend(["--extra-index-url", "https://download.pytorch.org/whl/cu128"])
    if installed:
        # Offline build from the exact tested environment; validate each installed RECORD hash.
        import base64
        import importlib.metadata as metadata
        packages.mkdir(parents=True, exist_ok=True)
        for line in lock.read_text(encoding="utf-8").splitlines():
            if not line or line.startswith("#"):
                continue
            name, version = line.split()[0].split("==")
            dist = metadata.distribution(name)
            if dist.version != version:
                raise RuntimeError(f"Installed dependency differs from lock: {name}")
            for item in dist.files or []:
                if ".." in item.parts or "__pycache__" in item.parts or item.suffix == ".pyc":
                    continue
                source = Path(dist.locate_file(item))
                if not source.is_file():
                    raise RuntimeError(f"Installed dependency file missing: {source}")
                if item.hash:
                    with source.open("rb") as stream:
                        actual = base64.urlsafe_b64encode(hashlib.file_digest(stream, item.hash.mode).digest()).rstrip(b"=").decode()
                    if actual != item.hash.value:
                        raise RuntimeError(f"Installed dependency RECORD mismatch: {source}")
                target = packages / str(item)
                target.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(source, target)
    else:
        subprocess.run(command, check=True)
    # Disable site entirely: importing it would execute user-site .pth files on this Python build.
    paths = ["python312.zip", ".", "Lib/site-packages", "Lib/site-packages/win32", "Lib/site-packages/win32/lib", "Lib/site-packages/Pythonwin", "Lib/site-packages/pywin32_system32", ".."]
    (folder / "python312._pth").write_text("\n".join(paths) + "\n", encoding="utf-8")
    for dll in (packages / "pywin32_system32").glob("*.dll"):
        shutil.copy2(dll, folder / dll.name)
    subprocess.run([str(folder / "python.exe"), "-c", "import fastapi,sherpa_onnx,pyaudio,keyboard,pyclip,psutil,websockets; import importlib.util; print('runtime imports OK'); " + ("import torch,qwen_asr;print(torch.__version__)" if cuda else "assert importlib.util.find_spec('torch') is None")], check=True)


def archive_tree(folder, destination):
    with zipfile.ZipFile(destination, "w", compression=zipfile.ZIP_DEFLATED, compresslevel=6, allowZip64=True) as bundle:
        for path in sorted(folder.rglob("*")):
            if path.is_file() and "__pycache__" not in path.parts:
                bundle.write(path, str(Path(folder.name) / path.relative_to(folder)))


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--version", default="1.0.0-alpha.1")
    parser.add_argument("--exe", type=Path, required=True)
    parser.add_argument("--cuda", action="store_true")
    parser.add_argument("--include-ffmpeg", action="store_true", help="Include the optional file-transcription component")
    parser.add_argument("--installed", action="store_true", help="Use the locked local environment after checking installed RECORD hashes")
    args = parser.parse_args()
    if sys.version_info[:2] != (3, 12) or sys.maxsize < 2**32:
        raise RuntimeError("Build with CPython 3.12 x64")
    out = ROOT / "dist/releases" / f"VoiceType-{args.version}-windows-x64"
    out.mkdir(parents=True, exist_ok=False)  # never silently overwrite a release
    shutil.copy2(args.exe, out / "VoiceType.exe")
    for directory in ("api", "client", "common", "config", "server"):
        for source in (ROOT / directory).rglob("*.py"):
            target = out / source.relative_to(ROOT)
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(source, target)
    for name in ("hot-zh.txt", "hot-en.txt", "hot-rule.txt", "README.md", "THIRD_PARTY.md"):
        shutil.copy2(ROOT / name, out / name)
    for name in ("start-runtime.ps1", "stop-dev.ps1", "mic_format_probe.py"):
        target = out / "scripts" / name
        target.parent.mkdir(exist_ok=True)
        shutil.copy2(ROOT / "scripts" / name, target)
    # FFmpeg is deliberately optional: it is only needed for file
    # transcription and can be shipped as a separately consented component.
    if args.include_ffmpeg:
        ffmpeg = ROOT / "tools/ffmpeg"
        if not (ffmpeg / "LICENSE.txt").exists() or not (ffmpeg / "SOURCE.txt").exists():
            raise RuntimeError("FFmpeg redistribution needs LICENSE.txt and exact SOURCE.txt")
        for source in (ffmpeg / "bin/ffmpeg.exe", ffmpeg / "bin/ffprobe.exe", ffmpeg / "LICENSE.txt", ffmpeg / "SOURCE.txt"):
            target = out / "tools/ffmpeg" / source.relative_to(ffmpeg)
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(source, target)
    helper = ROOT / "tools/windows_voice_capture/publish"
    if helper.joinpath("VoiceCaptureHelper.exe").is_file():
        shutil.copytree(helper, out / "tools/windows_voice_capture/publish")
    (out / "portable.json").write_text(json.dumps({"version": args.version, "platform": "windows-x64", "python": "3.12.10", "data": "data", "models": "models", "optional_components": {"ffmpeg": args.include_ffmpeg, "windows_voice_capture": helper.joinpath("VoiceCaptureHelper.exe").is_file()}}, ensure_ascii=False), encoding="utf-8")
    runtime(out / "runtime", installed=args.installed)
    archive = out.with_name(out.name + ".zip")
    archive_tree(out, archive)
    manifest = {"version": args.version, "cpu": {"name": archive.name, "bytes": archive.stat().st_size, "sha256": digest(archive)}}
    if args.cuda:
        component = out.parent / f"VoiceType-{args.version}-cuda"
        component.mkdir(exist_ok=False)
        runtime(component / "runtime-cuda", cuda=True, installed=args.installed)
        component_zip = component.with_name(component.name + ".zip")
        # Component archive contains runtime-cuda directly, so install at the portable root.
        archive_tree(component / "runtime-cuda", component_zip)
        manifest["cuda"] = {"name": component_zip.name, "bytes": component_zip.stat().st_size, "sha256": digest(component_zip)}
        if component_zip.stat().st_size > 1900000000:
            parts = []
            with component_zip.open("rb") as source:
                while source.tell() < component_zip.stat().st_size:
                    part = component_zip.with_name(component_zip.name + f".part{len(parts) + 1:02d}")
                    remaining = min(1900000000, component_zip.stat().st_size - source.tell())
                    with part.open("wb") as output:
                        while remaining:
                            chunk = source.read(min(8 * 1024 * 1024, remaining))
                            output.write(chunk)
                            remaining -= len(chunk)
                    parts.append({"name": part.name, "bytes": part.stat().st_size, "sha256": digest(part)})
            manifest["cuda"]["parts"] = parts
    (out.parent / f"VoiceType-{args.version}-components.json").write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    print(json.dumps(manifest, indent=2))


if __name__ == "__main__":
    main()

"""Collect build dependency notices without copying dependencies into source control."""
import json
import os
import shutil
import tomllib
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def collect():
    output = ROOT / "dist/third-party-licenses"
    output.mkdir(parents=True, exist_ok=True)
    inventory = []
    cargo = Path(os.environ.get("CARGO_HOME", Path.home() / ".cargo")) / "registry/src"
    locked = tomllib.loads((ROOT / "frontend/src-tauri/Cargo.lock").read_text(encoding="utf-8"))
    for package in locked["package"]:
        if not package.get("source", "").startswith("registry+"):
            continue
        key = f"{package['name']}-{package['version']}"
        candidates = list(cargo.glob(f"*/{key}"))
        if not candidates:
            raise RuntimeError(f"Missing Cargo source/license: {key}; run cargo fetch --locked")
        source = candidates[0]
        metadata = tomllib.loads((source / "Cargo.toml").read_text(encoding="utf-8"))["package"]
        inventory.append({"ecosystem": "cargo", "name": key, "license": metadata.get("license", ""), "repository": metadata.get("repository", "")})
        copy_notices(source, output / "cargo" / key)
    lock = json.loads((ROOT / "frontend/package-lock.json").read_text(encoding="utf-8"))
    for location, package in lock["packages"].items():
        if not location:
            continue
        source = ROOT / "frontend" / location
        if not source.is_dir():  # Optional packages for other operating systems.
            continue
        key = location.replace("node_modules/", "").replace("/", "_")
        inventory.append({"ecosystem": "npm", "name": key, "version": package.get("version"), "license": package.get("license", "")})
        copy_notices(source, output / "npm" / key)
    (output / "inventory.json").write_text(json.dumps(inventory, ensure_ascii=False, indent=2), encoding="utf-8")


def copy_notices(source, destination):
    names = ("LICENSE", "LICENCE", "COPYING", "NOTICE", "COPYRIGHT", "AUTHORS")
    for item in source.iterdir():
        if item.is_file() and item.name.upper().startswith(names):
            destination.mkdir(parents=True, exist_ok=True)
            shutil.copy2(item, destination / item.name)


if __name__ == "__main__":
    collect()

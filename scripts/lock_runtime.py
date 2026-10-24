"""Freeze the tested environment's dependency closure and upstream artifact hashes."""
import concurrent.futures
import importlib.metadata as metadata
import json
import re
from pathlib import Path
from urllib.parse import unquote
from urllib.request import urlopen
from packaging.requirements import Requirement
from packaging.utils import canonicalize_name

ROOT = Path(__file__).resolve().parents[1]


def closure(path):
    queue = []
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.split("#")[0].strip()
        if line.startswith("-r "):
            queue.extend(closure(path.parent / line[3:].strip()))
        elif line:
            queue.append(Requirement(line).name)
    selected = {}
    while queue:
        name = queue.pop()
        key = canonicalize_name(name)
        if key in selected:
            continue
        dist = metadata.distribution(name)
        selected[key] = dist.version
        for dependency in dist.requires or []:
            req = Requirement(dependency)
            if req.marker is None or req.marker.evaluate({"extra": ""}):
                queue.append(req.name)
    return selected


def hashes(item):
    name, version = item
    if name == "torch" and "+cu128" in version:
        with urlopen("https://download.pytorch.org/whl/cu128/torch/", timeout=60) as response:
            index = response.read().decode()
        candidates = re.findall(r'href="([^\"]+)"', index)
        suffix = f"torch-{version}-cp312-cp312-win_amd64.whl"
        values = [url.split("#sha256=")[1] for url in candidates if unquote(url.split("#")[0]).endswith(suffix) and "#sha256=" in url]
    else:
        with urlopen(f"https://pypi.org/pypi/{name}/{version}/json", timeout=60) as response:
            info = json.load(response)
        values = sorted({row["digests"]["sha256"] for row in info["urls"]})
    if not values:
        raise RuntimeError(f"No upstream hash: {name}=={version}")
    return name, f"{name}=={version} " + " ".join("--hash=sha256:" + value for value in values)


if __name__ == "__main__":
    for kind in ("cpu", "cuda"):
        versions = closure(ROOT / f"requirements-{kind}.txt")
        with concurrent.futures.ThreadPoolExecutor(max_workers=8) as pool:
            lines = sorted(pool.map(hashes, versions.items()))
        target = ROOT / f"requirements-{kind}.lock"
        target.write_text("# Tested dependency closure. Regenerate with scripts/lock_runtime.py.\n" + "\n".join(line for _, line in lines) + "\n", encoding="utf-8")
        print(target.name, len(lines), flush=True)

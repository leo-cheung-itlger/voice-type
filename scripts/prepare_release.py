"""Merge and verify CPU/CUDA artifacts before uploading a release."""
import argparse
import hashlib
import json
import re
from pathlib import Path


def prepare(folder, version):
    if not re.fullmatch(r"\d+\.\d+\.\d+(?:-[A-Za-z0-9.-]+)?", version):
        raise ValueError("Invalid release version")
    path = folder / f"VoiceType-{version}-components.json"
    manifest = json.loads(path.read_text(encoding='utf-8'))
    cuda = json.loads((folder / f"VoiceType-{version}-cuda-manifest.json").read_text(encoding='utf-8'))
    if manifest['version'] != version or cuda['version'] != version:
        raise ValueError('Artifact versions differ')
    manifest['cuda'] = cuda['cuda']
    checksums = []
    for spec in [manifest['cpu'], manifest['cuda']]:
        combined = hashlib.sha256()
        total = 0
        for item in spec.get('parts') or [spec]:
            name = item['name']
            if Path(name).name != name or any(c in name for c in '/\\:'):
                raise ValueError('Invalid artifact name')
            artifact = folder / name
            checksum = hashlib.sha256()
            with artifact.open('rb') as stream:
                while chunk := stream.read(8 * 1024 * 1024):
                    checksum.update(chunk)
                    combined.update(chunk)
            if artifact.stat().st_size != item['bytes'] or checksum.hexdigest() != item['sha256']:
                raise ValueError(f'Artifact verification failed: {name}')
            total += artifact.stat().st_size
            checksums.append(f'{checksum.hexdigest()}  {name}')
        if total != spec['bytes'] or combined.hexdigest() != spec['sha256']:
            raise ValueError('Combined component verification failed')
    path.write_text(json.dumps(manifest, indent=2), encoding='utf-8')
    checksums.append(f'{hashlib.sha256(path.read_bytes()).hexdigest()}  {path.name}')
    (folder / 'SHA256SUMS.txt').write_text('\n'.join(checksums) + '\n', encoding='utf-8')
    print(json.dumps(manifest, indent=2))


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('folder', type=Path)
    parser.add_argument('version')
    args = parser.parse_args()
    prepare(args.folder, args.version)

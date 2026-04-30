import argparse
import json
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from api.api_server import _benchmark_models, _benchmark_path
from config.settings import MODEL_DIR_NAMES


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Benchmark configured VoiceType ASR models and write data/model_benchmark.json."
    )
    parser.add_argument(
        "--audio-file",
        default="",
        help="Audio fixture to transcribe. Defaults to the API benchmark fixture.",
    )
    parser.add_argument(
        "--models",
        nargs="*",
        default=None,
        help="Optional model ids to benchmark. Defaults to every configured model id.",
    )
    parser.add_argument(
        "--list-models",
        action="store_true",
        help="Print configured model ids and exit.",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    if args.list_models:
        print(json.dumps(list(MODEL_DIR_NAMES.keys()), ensure_ascii=False, indent=2))
        return 0

    result = _benchmark_models(
        models=args.models,
        audio_file=args.audio_file or None,
    )
    print(json.dumps(result, ensure_ascii=False, indent=2))
    print(f"wrote {_benchmark_path()}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

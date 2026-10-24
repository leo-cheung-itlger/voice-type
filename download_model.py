"""命令行下载入口，与应用共用模型格式、校验和断点续传。"""
import argparse
import time
from common.model_catalog import CATALOG
from common.model_download import start_download, jobs


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("model", nargs="?", default="sensevoice", choices=[key for key, spec in CATALOG.items() if spec["implemented"]])
    parser.add_argument("--all", action="store_true", help="下载全部已实现模型（需要较大磁盘空间）")
    args = parser.parse_args()
    for model in ([key for key, spec in CATALOG.items() if spec["implemented"]] if args.all else [args.model]):
        start_download(model)
        previous = ""
        while jobs[model]["status"] == "running":
            job = jobs[model]
            message = f"{model}: {job['message']} {job['downloaded_bytes'] / 1024**2:.1f} MB"
            if message != previous:
                print(message, flush=True)
                previous = message
            time.sleep(1)
        if jobs[model]["status"] != "done":
            raise SystemExit(jobs[model]["error"])
        print("已安装:", jobs[model]["target_dir"])


if __name__ == "__main__":
    main()

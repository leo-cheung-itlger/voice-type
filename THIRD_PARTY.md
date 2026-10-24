# 第三方组件

此文件说明来源；具体许可文本以发行包内各组件的 LICENSE、NOTICE 和 `.dist-info/licenses/` 为准。构建脚本保留依赖元数据及许可文件。模型由用户单独下载，不随源码或 CPU 基础包分发。

| 组件 | 来源 | 许可说明 |
| --- | --- | --- |
| CPython 3.12.10 Windows embeddable x64 | [Python 官方发行页](https://www.python.org/downloads/release/python-31210/) | PSF License；发布包保留 LICENSE.txt。后续安全版本升级仍需测试 |
| Vue、Vue Router、Pinia、Vite | 各官方项目；版本由 frontend/package-lock.json 固定 | MIT |
| Tauri、相关 Rust crates | [Tauri](https://github.com/tauri-apps/tauri)；Cargo.lock 固定 | MIT／Apache-2.0，其他 crates 按各自许可 |
| FastAPI、Starlette、Uvicorn、Pydantic、websockets | PyPI 官方包；requirements-cpu.lock 固定并包含上游哈希 | 按各包元数据，常见 MIT／BSD |
| NumPy、SciPy、sherpa-onnx、PyAudio、keyboard、pyclip、psutil、pywin32 | PyPI 官方包 | 按包内许可；sherpa-onnx 为 Apache-2.0，PyAudio 使用 PortAudio |
| Qwen ASR、Transformers、Accelerate、PyTorch 及依赖 | 官方 PyPI／PyTorch CUDA 12.8 索引；requirements-cuda.lock | 可选 GPU 运行组件保留相应许可；包含 NVIDIA CUDA 库的组件还受其再分发条款约束 |
| .NET 自包含录音辅助程序 | [dotnet/runtime](https://github.com/dotnet/runtime) | 保留 publish 目录内第三方声明；应用代码在 tools/windows_voice_capture |
| FFmpeg 8.1 essentials build | [Gyan builds](https://www.gyan.dev/ffmpeg/builds/)；[FFmpeg n8.1 源码](https://github.com/FFmpeg/FFmpeg/tree/n8.1) | 当前本机构建为 GPLv3、独立进程。公开二进制发行前需收集对应源码、外部库版本和声明；仅有网页链接不能视为该验收已完成 |

## 模型来源

1. SenseVoice：下载 sherpa-onnx 官方 `sherpa-onnx-sense-voice-zh-en-ja-ko-yue-int8-2024-07-17.tar.bz2`，校验 SHA-256，安装 `model.int8.onnx` 与 `tokens.txt`。归档中的 LICENSE 指向 [FunASR 许可说明](https://github.com/modelscope/FunASR#license)，使用前应阅读其模型条款。
2. Paraformer：sherpa-onnx 官方 `sherpa-onnx-paraformer-zh-2023-03-28.tar.bz2`，仅安装 INT8 ONNX 和词表；模型条款同样应查阅其发布说明。
3. Qwen：[Qwen3-ASR 0.6B](https://huggingface.co/Qwen/Qwen3-ASR-0.6B)、[1.7B](https://huggingface.co/Qwen/Qwen3-ASR-1.7B)。下载固定仓库 revision，并校验 LFS 权重哈希。模型许可由其模型卡和仓库许可决定。

模型权重、运行组件、音视频、日志和本地配置不进入本项目 Git 历史。

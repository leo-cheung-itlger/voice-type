# VoiceType

Windows 本地语音输入工具。按住快捷键说话，松开后识别并输入文字；也可批量转录音视频，导出 TXT、JSON 和 SRT。

**当前为开发测试版，尚无通过全部验收的独立便携发行版。** 源码公开在 [GitHub](https://github.com/leo-cheung-itlger/voice-type)。Windows 10／11 干净环境、低配实机和真实快捷键到输入的便携包验收仍需完成。

## 硬件与模型

| 环境 | 推荐模型 | 实际运行方式 |
| --- | --- | --- |
| 无独显、AMD／Intel 显卡、CUDA 不可用 | SenseVoice INT8 | CPU |
| 中文低延迟输入 | Paraformer 中文 | CPU，自动识别中英，不支持强制指定语言 |
| NVIDIA CUDA 可用 | Qwen3-ASR 0.6B | CUDA；需要可选 GPU 运行组件 |
| 更重视质量 | Qwen3-ASR 1.7B | 手动选择，内存／显存需求更高 |

不支持 AMD／Intel GPU 加速。GGUF、Vulkan 和 FunASR Nano 后端仍在开发中，界面禁止选择和下载。尚未公布最低内存／显存配置；不能把开发电脑上的速度视为低配性能保证。

SenseVoice 的官方 ONNX 模型支持普通话、英语、粤语、日语、韩语：[模型说明](https://k2-fsa.github.io/sherpa/onnx/sense-voice/pretrained.html)。首次下载约 163 MB，安装后模型文件约 228 MiB。Qwen 权重约 1.3 GB／3.5 GB，界面显示的值为估计，实际下载进度使用文件清单。

## 使用流程

1. 打开应用，在“设置 → 识别设置”查看推荐，点击下载或导入对应模型。打开界面无需先加载模型。
2. 选择“自动选择／CPU／NVIDIA GPU”和“识别语言”，点击“应用并重启识别”。默认语言是普通话；自动检测不强制语言。
3. 按住设置中的快捷键说话，松开后输入。录音、识别和转录期间不能切换模型。
4. 在“转录”选择文件。任务保存创建时的模型、语言和硬件策略；更换模型的文件任务会暂停快捷键输入，完成后恢复原服务。

“自动选择”允许 Qwen 加载失败后使用已安装的 SenseVoice CPU 模型，并显示失败原因。没有 CPU 模型时会提示下载。手动选择 NVIDIA GPU 时，CUDA 不可用会明确失败。原来的显式 CPU／严格 GPU 配置会保留。

语言选项用于语音识别，不提供翻译。指定普通话是否提高准确率或速度需要按自己的音频验证。

便携包用户无需安装系统 Python、PyTorch 或 .NET SDK。若 Windows 缺少 WebView2，请安装 [Microsoft 官方 WebView2 Evergreen Runtime](https://developer.microsoft.com/microsoft-edge/webview2/#download-section)，然后重新打开应用。Windows 语音增强不可用时会退回基础录音。

## 数据与隐私

默认音频识别在本机进行。模型下载需要连接 GitHub 或 Hugging Face；只有启用文件转录的 AI 润色时，文本才会发送到用户配置的服务。

便携目录中的 `data/` 保存设置、历史、上传缓存和录音，`models/` 保存下载的模型，`logs/` 保存诊断日志。导入的模型保留在原目录，移动应用时需一并处理。不要把这些目录和 API key 提交到 Git。

## 源码开发

需要 Windows x64、Python 3.12、Node.js 和 npm。构建桌面壳另需 Rust、MSVC Build Tools；构建录音增强组件另需 .NET SDK，最终用户无需安装 SDK。

```powershell
python -m venv venv
.\venv\Scripts\python.exe -m pip install --require-hashes -r requirements-cpu.lock
cd frontend
npm ci
cd ..
.\scripts\start-dev.ps1
```

浏览器打开 [本地界面](http://127.0.0.1:55343/#/)，然后在设置下载模型。CPU 基础依赖不安装 PyTorch。开发环境启用 Qwen：

```powershell
.\venv\Scripts\python.exe -m pip install --require-hashes -r requirements-cuda.lock --extra-index-url https://download.pytorch.org/whl/cu128
```

开发模型默认放在项目相邻的 `models/`，便携模式使用发布目录内的 `models/`。可用 `VOICETYPE_MODELS_DIR`、`VOICETYPE_DATA_DIR` 指定位置。

完整操作、构建和验收命令见 [RUNBOOK](RUNBOOK.md)，最新验证范围见 [PROJECT_STATUS](PROJECT_STATUS.md)，依赖和模型许可见 [THIRD_PARTY](THIRD_PARTY.md)。本仓库尚未指定项目源码许可证；公开可读不代表已授权任意再分发。

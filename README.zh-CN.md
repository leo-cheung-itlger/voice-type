# VoiceType 中文说明

[English README](README.md)

<p align="center">
  <img src="frontend/src-tauri/icons/icon.png" alt="VoiceType logo" width="128">
</p>

<p align="center">
  <strong>面向 Windows 的本地语音输入工具</strong><br>
  按住快捷键说话，松开后把文字输入到当前光标位置。
</p>

> **Alpha 测试版：** 当前项目仍在开发测试阶段。Windows 10/11 干净环境、低性能电脑和一键安装包还没有完成全部验收，请把它当作早期体验版本使用。

## 它能做什么

VoiceType 是一个 Windows 桌面语音输入工具。按住快捷键说话，松开后识别结果会输入到当前正在使用的应用中。

- **默认本地识别：** 音频通常在本机处理。
- **新手优先：** 选择语言、下载推荐模型，然后开始说话。
- **自动选择硬件：** CPU 始终作为回退方案；兼容的 NVIDIA 显卡可以安装可选 CUDA 运行组件。
- **原生桌面窗口：** 正式版本使用 Tauri 窗口并支持托盘；浏览器端口只用于开发。
- **文件转录：** 安装可选 FFmpeg 组件后，可以转录音频和视频文件。

## 当前界面预览

![VoiceType 当前界面预览](voicetype-validation.png)

这张图是当前开发界面预览，用于展示产品方向，不代表所有功能已经通过干净系统发行验收。

## 当前使用方式

目前公开仓库主要提供源码和开发说明，经过完整验收的独立安装包还没有发布。

1. 准备 Windows x64、Python 3.12、Node.js 和 npm。
2. 按 [RUNBOOK.md](RUNBOOK.md) 创建 CPU 开发环境。
3. 启动开发界面，在“设置 → 识别设置”下载模型。
4. 默认识别语言是普通话，一般不需要修改。
5. 按住快捷键说话，松开后输入识别结果。

正式桌面版本通过 `VoiceType.exe` 启动。`start-live-ui.ps1` 和 `http://127.0.0.1:55343` 仅用于开发联调。

## 模型与硬件

| 电脑情况 | 推荐模型 | 运行方式 |
| --- | --- | --- |
| 没有 NVIDIA 显卡、使用 AMD/Intel 显卡或 CUDA 不可用 | SenseVoice INT8 | CPU |
| NVIDIA CUDA 环境兼容 | Qwen3-ASR 0.6B | 可选 CUDA 运行组件 |
| 更重视识别质量 | Qwen3-ASR 1.7B | 高级设置手动选择，内存占用更高 |
| CPU 电脑做文件转录 | Paraformer 中文 | CPU；语言限制较少 |

默认运行方式是“自动选择”。GPU 组件或 GPU 模型加载失败时，VoiceType 会显示原因，并可以回退到已经安装的 SenseVoice CPU 模型。GPU 组件只有在用户确认后才会下载。

模型下载会优先使用有完整文件清单的 ModelScope 镜像，失败后回退到 Hugging Face 官方源，并校验 SHA-256。GGUF、Vulkan 和 FunASR Nano 后端仍在开发中，当前不会显示为可用选项。

当前识别语言包括普通话、自动检测、英语、粤语、日语和韩语。这是识别语言设置，不是翻译功能。

## 隐私

- 默认语音识别在本机完成。
- 下载模型需要连接模型来源网站。
- 文件转录中的 AI 润色只有在用户主动配置后，才会把文字发送到对应服务。
- 便携目录中的数据、模型、录音和日志保存在应用自己的目录内。

## 已知限制

- 暂不支持 AMD/Intel GPU 加速。
- 低配实机和 Windows 10/11 干净环境还需要专门验收。
- 当前没有公布可保证的最低内存或显存要求。
- 仓库虽然公开，但项目许可证尚未确定；公开可见不等于允许任意再分发。

## 开发与文档

开发环境、打包和验收命令见 [RUNBOOK.md](RUNBOOK.md)。项目当前状态和未完成验收见 [PROJECT_STATUS.md](PROJECT_STATUS.md)。第三方依赖和许可证说明见 [THIRD_PARTY.md](THIRD_PARTY.md)。

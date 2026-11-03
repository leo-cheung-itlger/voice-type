# PROJECT_STATUS

## 公开便携版发布准备（2026-11-03）

用户已确认：源码采用 MIT；发布 Windows x64 CPU 基础包，不内置模型和 FFmpeg；首次打开引导下载 SenseVoice；NVIDIA 用户查看组件准确大小及模型估算大小后确认下载，验证驱动兼容性后自动启用 Qwen 0.6B，保留 CPU 模型备用。使用 GitHub Actions 分别构建 CPU／CUDA。公开下载核验完成后清理本地临时发行产物，本地不长期保留正式包。

已实现首次使用引导、绑定确认哈希的 GPU 下载接口、安装前 GPU 验证及成功后的下载副本清理；新增独立 CUDA 打包、云构建和第三方声明收集脚本。当前 18 项 Python 回归、Python 语法检查、前端类型检查及生产构建通过。云构建、运行界面及本次便携包验收仍待执行，尚未发布新二进制。

## 本地构建存储（2026-11-03）

用户决定暂停 VoiceType 开发，接受以后重新配置与编译。本轮已删除 `venv/`、`frontend/node_modules/`、`frontend/dist/`、全部 `dist/`、`tools/ffmpeg/`、录音辅助程序的 `bin/obj/publish`、日志、Python/测试/浏览器缓存及 `vs_BuildTools.exe`。合计移除 7,016,324,398 字节（6.534 GiB），目录从 6.640 GiB 缩至约 108.24 MiB（文档更新前）。源码、Git、全部 data、依赖锁与已有文档修改保留，665 份保留文件的 SHA-256 汇总前后一致。未启动或重建应用；当前没有可直接使用的 VoiceType 运行环境或本地发行包。恢复步骤见 RUNBOOK 的“暂停开发后的恢复”。

本机 PATH 已有系统 FFmpeg/ffprobe；项目内副本已清理。文件转录会使用系统组件，普通快捷键语音输入无需 FFmpeg。正式便携包内置 Python 运行时，最终用户无需安装开发用 venv。

此前清理记录：

经用户确认，已清理 `frontend/src-tauri/target`、`target-codex-build7` 与 local3 CUDA ZIP 的两个分卷；随后清理 local1/local2 旧CPU发布目录、local2 CUDA展开目录及“便携验证 空格”测试副本。测试副本的4份配置/文字JSON已保留于 `data/portable-validation/retained-config-20261101/`。

用户同时确认清理旧录音：`data/recordings/` 中音频及 `data/archive/` 中WAV已删除，录音目录重建为空；主配置、历史文字与归档JSON保留，历史音频无法继续回放。当时保留开发环境与 local3 完整发布目录，随后按上述暂停开发决定继续清理；CPU/CUDA ZIP 已于2026-11-03较早一轮删除。此前执行记录见[空间优化收益表](../computer-organization/空间优化收益表.md)。

## 当前交付状态（2026-10-24）

Windows x64 便携测试版的硬件策略、语言、模型管理和打包代码已实现。源码仓库为 https://github.com/leo-cheung-itlger/voice-type 。**二进制预发行尚未发布，不能宣称下载即用或全面硬件兼容。**

## 当前架构与决策

- Vue 3 / Vite / Pinia、Tauri 2 桌面壳、Python API / ASR / 快捷键客户端保持不变。端口为 ASR 55341、API 55342、开发 UI 55343，仅监听本机。
- API 可独立打开，首次启动不预加载模型。设置下载或导入后，使用“应用并重启识别”。运行方式为 auto / cpu / cuda；默认语言 zh，原显式 CPU／严格 GPU 配置保留。
- CPU 基础路线为 sherpa-onnx SenseVoice INT8，Paraformer 是中英自动识别选项。Qwen 0.6B／1.7B 使用可选 PyTorch CUDA 组件。GGUF / Vulkan / FunASR Nano 后端不可选。模型能力和格式的唯一代码定义在 common/model_catalog.py。
- 同模型文件转录复用 ASR；切换模型／语言的任务暂停快捷键输入，串行执行并恢复服务。任务保存创建时的语言和硬件策略；旧任务不补写语言。SRT 仍是分块近似时间戳。
- 活动租约保护录音、推理、转录和切换。配置单独保存 server 部分，避免覆盖加载期间修改的麦克风设置。
- 便携包使用应用内隔离 Python，CPU 不含 PyTorch；CUDA 组件另下载。模型、数据、日志位于便携目录；导入模型仍在原目录。启动脚本已恢复并校验端口归属。
- Qwen Hub 模型下载会先查询 ModelScope 文件清单并校验 SHA-256，清单不完整或镜像失败时回退 Hugging Face；任务会记录来源。未实现的 GGUF/Vulkan 模型仍被目录和接口拒绝。
- CPU 锁定依赖已移除 SciPy；麦克风诊断在安装开发依赖时才使用 SciPy，并有 NumPy 备用重采样。FFmpeg 从默认便携包改为可选构建项，未安装时文件转录显示可理解的组件提示。
- Windows MediaCapture 语音增强默认启用，缺失／不支持时回退 PyAudio；打包包含自包含录音增强程序，用户不需要 .NET SDK。现有麦克风热更新、单声道选择、自动增益和录音归档保留。
- 日常开发入口为 VoiceType-live-ui.bat；便携 EXE 仅用于发布验收。构建标识和 PID 在高级诊断中查看。
- 托盘菜单使用中文；`start-live-ui.ps1` 明确是开发浏览器入口，发行包仍由 `VoiceType.exe` 打开原生 Tauri 窗口。应用图标和托盘图标已替换为 VoiceType logo 的多尺寸 PNG/ICO/ICNS。

## 已执行验证

- Python 编译及 tests/test_runtime_contracts.py 的 13 项回归通过（含中文词表路径、历史保留、停止时健康检查竞态）：旧配置迁移、语言／模型契约、下载续传、活动互斥、自动回退与严格 GPU 失败、失败回滚、并发保存、启动互斥。
- 前端类型检查和生产构建通过；主入口约 120.8 KB，gzip 46.7 KB。Tauri release EXE、自包含录音增强组件构建通过。
- 官方 SenseVoice INT8 下载、SHA256 校验、安装及本机 CPU 推理通过。嵌入式 CPU Python 能导入录音／ASR／API 所需依赖，且找不到 PyTorch；关闭 site 后不再读取系统用户包。
- 同一组官方测试 WAV 完成 zh / auto / en / yue 两套实测（SenseVoice CPU、Qwen 0.6B CUDA），两套文件转录均完成；不是逐字准确率评测，不以非空文本证明高准确率。
- SenseVoice：5.1–7.2 秒音频，预热后 0.086–0.140 秒，进程 RSS 约 354–361 MiB；Qwen CUDA：预热后约 0.598–0.790 秒，RSS 约 2.24–2.27 GiB。这是开发机结果，不能外推最低配置。首次识别和完整服务重启明显更慢。
- 测试原始结果保存在忽略的 data/portable-validation/cpu.json、cuda.json，复现脚本 scripts/validate_runtime.py。语言固定与自动检测的少量对照不足以承诺提速或提升准确率。
- 独立代码审查发现并修复了启动路径绕过切换锁、CPU 模式误报 Qwen 兼容、保存时覆盖客户端设置三个问题；相关回归均通过。

- 便携内置 CPU 运行时已在中文／空格目录、精简 PATH 下完成打开界面、校验安装 SenseVoice、四种语言实测及文件转录。发现并修复 sherpa 词表中文路径问题；这仍不是干净系统验收。
- 469×719 与 1200×850 浏览器窗口无横向溢出，模型入口和普通话默认值正确，最终检查无页面异常。基础录音与自包含 Windows 语音增强测试均成功（静音环境不判断识别质量），无需系统 .NET SDK。实际无效模型应用返回错误并恢复 SenseVoice，之后可重新识别。
- 前端实时列表上限 200，历史查询每次最多 1000 条，历史元数据完整保留；统计缓存避免重复计算。JSON 历史全量写入仍随数量增长，后续可按实测迁移索引存储。
- 本轮新增验证：`python -m compileall`、ModelScope Qwen 文件清单及 SHA-256 字段检查、CPU lock 无 SciPy 检查、`npm run build` 和 `git diff --check` 均通过。当前环境没有 Cargo，未能执行 Tauri Rust 构建。

- 单逻辑 CPU 亲和性、单推理线程的模拟中，SenseVoice 5.592 秒样本预热后为 0.143–0.149 秒，RSS 350 MiB；仍是高性能开发机的受限测试。
- 本地 CPU ZIP 约 203 MB（含 FFmpeg、自包含录音增强和 25 个锁定依赖），可选 CUDA 组件约 3.01 GB（99 个依赖），提供分卷。组件体积来自运行依赖，未计入模型权重。

- Qwen → SenseVoice 文件任务完成后已实际恢复 Qwen；本机 GPU 推理分配约 1510 MiB、保留 1836 MiB、峰值分配 1794 MiB（PyTorch 进程指标，不是整机显存占用）。浏览器停止／重新启动后恢复录音状态，最终检查无新页面异常或 HTTP 5xx。

## 发布前剩余验收

1. Windows 10／11 干净环境，从中文和空格路径验证独立启动、下载、快捷键录音到目标应用输入、停止再启动、增强录音不可用时回退、WebView2 缺失引导。
2. 真正无 CUDA／无 PyTorch 机器及低配实机。开发机隔离运行时和受限线程测试只能补充证据，不能替代实机。
3. 实际显存不足、驱动不兼容恢复；当前有故障模拟回归，不能称已覆盖所有驱动。
4. Paraformer 和 Qwen 1.7B 本轮未做完整运行验收；日语、韩语尚未逐项实测。
5. 发行包采用 MIT，默认不分发 FFmpeg。云构建收集 Rust／前端依赖声明，保留 Python wheel 与 .NET 许可；发行产物中仍需核验材料完整性。
6. 本轮没有重新验证真实 F1 按键到其他应用粘贴、托盘退出和干净系统的桌面 WebView。旧版录音验证不替代新便携包验收。

## 下一步

完成云构建和本次便携包验收后发布，再清理本地临时产物；以上历史验证不替代新版本验收。

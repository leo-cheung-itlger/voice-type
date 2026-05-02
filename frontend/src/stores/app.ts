import { defineStore } from 'pinia'
import { computed, ref } from 'vue'

export interface HistoryEntry {
  text: string
  task_id: string
  timestamp: number
  delay: number
  duration_seconds?: number
  audio_path?: string
  transcript_path?: string
  model?: string
  marked?: boolean
  marked_words_text?: string
}

export interface ErrorMark {
  text: string
  marked_text: string
  timestamp: number
}

export interface AppConfig {
  server: {
    host: string
    port: number
    model: string
    model_dir: string
    gpu: boolean
    gpu_required: boolean
    allow_cpu_fallback: boolean
    gpu_backend: 'vulkan' | 'dml' | 'cuda'
  }
  client: {
    server_host: string
    server_port: number
    shortcut_key: string
    sample_rate: number
    channels: number
    input_device_index: number
    input_device_name: string
    input_device_host_api: string
    input_device_sample_rate: number
    output_mode: 'clipboard' | 'keyboard' | 'hybrid'
    save_audio: boolean
    audio_dir: string
    archive_root: string
    min_press_seconds: number
    hotword_files: string[]
    notification_enabled: boolean
    notification_sound: boolean
  }
  api?: {
    host: string
    port: number
    frontend_port: number
  }
}

export interface ModelEntry {
  id: string
  name: string
  path: string
  exists: boolean
  backend?: string
  role?: string
  acceleration?: string
  download_url?: string
  blocking_reason?: string
  gpu_required_supported?: boolean
  recommended_for?: string[]
  benchmark?: ModelBenchmark | null
  benchmarks?: Record<string, ModelBenchmark>
}

export interface ModelBenchmark {
  model: string
  exists: boolean
  ok: boolean
  loading_seconds?: number
  recognition_seconds?: number
  total_seconds?: number
  inference_seconds?: number
  actual_gpu?: boolean
  acceleration?: string
  backend?: string
  text?: string
  cuda_available?: boolean
  error?: string
  updated_at?: number
}

export interface HardwareInfo {
  cpu: string
  memory_gb: number | null
  nvidia_gpu: boolean
  gpus: { name: string; memory_total_mb?: number; driver_version?: string }[]
  torch: {
    available: boolean
    version: string
    cuda_available: boolean
    cuda_version: string | null
    error: string
  }
  vulkan?: {
    available: boolean
    model_dir?: string
    gguf_files?: string[]
    error?: string
  }
  gpu_required?: boolean
  allow_cpu_fallback?: boolean
  blockers?: string[]
  runtime_ready?: boolean
  recommendation: string
}

export interface AccelerationState {
  label: string
  detail: string
  active: boolean
  backend: AppConfig['server']['gpu_backend'] | 'cpu'
  cudaReady: boolean
  vulkanSelected: boolean
  blocks: string[]
}

export interface AccelerationRecommendation {
  model: string
  modelName: string
  gpu: boolean
  gpu_backend: AppConfig['server']['gpu_backend']
  reason: string
  benchmarkSeconds: number | null
}

export interface FfmpegStatus {
  available: boolean
  ffmpeg: string
  ffprobe: string
  supported_extensions: string[]
  message: string
}

export interface LlmConfig {
  base_url: string
  model: string
  api_key: string
  temperature: number
  max_segment_chars: number
}

export interface AudioInputDevice {
  index: number
  name: string
  host_api: string
  host_api_index: number
  channels: number
  default_sample_rate: number
  is_default: boolean
  selected: boolean
  recommended: boolean
  reason: string
  level_supported: boolean
}

export interface AudioInputDevicesResponse {
  available: boolean
  devices: AudioInputDevice[]
  default_index: number
  selected_index: number
  selected_name: string
  selected_exists: boolean
  recommended_count: number
  error: string
}

export interface AudioInputTestResult {
  ok: boolean
  message: string
  has_signal: boolean
  device_index?: number
  device_name?: string
  host_api?: string
  sample_rate?: number
  seconds?: number
  bytes?: number
  samples?: number
  rms?: number
  peak?: number
  rms_ratio?: number
  peak_ratio?: number
  audio_wav_base64?: string
}

export interface TranscriptionTask {
  task_id: string
  status: 'queued' | 'transcribing' | 'polishing' | 'completed' | 'failed' | 'cancelled'
  created_at: number
  updated_at: number
  progress: number
  input_files: string[]
  files: {
    path: string
    status: string
    error?: string
    progress?: number
    output_dir?: string
    outputs?: Record<string, string>
  }[]
  model: string
  output_dir: string
  formats: string[]
  polish: boolean
  polish_mode: string
  error?: string
}

function isDevFrontendHost() {
  const host = window.location.hostname
  const port = window.location.port
  return (host === '127.0.0.1' || host === 'localhost') && port === '55343'
}

const API_BASE = (() => {
  const configured = import.meta.env.VITE_API_BASE
  if (configured) return configured
  const protocol = window.location.protocol
  if (protocol !== 'http:' && protocol !== 'https:') return 'http://127.0.0.1:55342/api'
  if (isDevFrontendHost()) return '/api'
  return 'http://127.0.0.1:55342/api'
})()

const WS_RECOGNITION_URL = (() => {
  const configured = import.meta.env.VITE_WS_RECOGNITION_URL
  if (configured) return configured
  if (isDevFrontendHost()) {
    const protocol = window.location.protocol === 'https:' ? 'wss' : 'ws'
    return `${protocol}://${window.location.host}/ws/recognition`
  }
  return 'ws://127.0.0.1:55342/ws/recognition'
})()

const defaultConfig: AppConfig = {
  server: {
    host: '0.0.0.0',
    port: 55341,
    model: 'qwen3-asr-1.7b',
    model_dir: '',
    gpu: true,
    gpu_required: true,
    allow_cpu_fallback: false,
    gpu_backend: 'cuda',
  },
  client: {
    server_host: '127.0.0.1',
    server_port: 55341,
    shortcut_key: 'caps_lock',
    sample_rate: 48000,
    channels: 1,
    input_device_index: -1,
    input_device_name: '',
    input_device_host_api: '',
    input_device_sample_rate: 0,
    output_mode: 'clipboard',
    save_audio: true,
    audio_dir: '',
    archive_root: '',
    min_press_seconds: 0.1,
    hotword_files: ['hot-zh.txt', 'hot-en.txt', 'hot-rule.txt'],
    notification_enabled: true,
    notification_sound: true,
  },
  api: {
    host: '127.0.0.1',
    port: 55342,
    frontend_port: 55343,
  },
}

export const useAppStore = defineStore('app', () => {
  const serverRunning = ref(false)
  const clientRunning = ref(false)
  const serverPid = ref<number | null>(null)
  const clientPid = ref<number | null>(null)
  const serverManaged = ref(false)
  const clientManaged = ref(false)
  const serverPortOpen = ref(false)
  const serverConflict = ref(false)
  const clientConflict = ref(false)
  const serverProcessCount = ref(0)
  const clientProcessCount = ref(0)
  const history = ref<HistoryEntry[]>([])
  const errorMarks = ref<ErrorMark[]>([])
  const wsConnected = ref(false)
  const currentPartial = ref('')
  const topWords = ref<{ word: string; count: number }[]>([])
  const config = ref<AppConfig>(structuredClone(defaultConfig))
  const models = ref<ModelEntry[]>([])
  const hardware = ref<HardwareInfo | null>(null)
  const benchmarks = ref<Record<string, ModelBenchmark>>({})
  const benchmarkingModels = ref<string[]>([])
  const logs = ref<{ file: string; line: string }[]>([])
  const recentIssues = ref<{ file: string; line: string }[]>([])
  const hotwordContent = ref<Record<string, string>>({})
  const selectedHotword = ref('hot-zh.txt')
  const ffmpeg = ref<FfmpegStatus | null>(null)
  const llmConfig = ref<LlmConfig>({
    base_url: 'https://api.openai.com/v1',
    model: '',
    api_key: '',
    temperature: 0.2,
    max_segment_chars: 1800,
  })
  const transcriptions = ref<TranscriptionTask[]>([])
  const audioInputDevices = ref<AudioInputDevicesResponse | null>(null)
  const audioInputTest = ref<AudioInputTestResult | null>(null)
  const audioInputTesting = ref(false)
  const playingTaskId = ref('')
  const runtimeDiagnostics = ref('')
  const runtimeRestarting = ref(false)
  const lastError = ref('')
  const toastMessage = ref('')
  let toastTimer: ReturnType<typeof setTimeout> | null = null
  let activeAudio: HTMLAudioElement | null = null
  const ws: { current: WebSocket | null } = { current: null }

  const latestEntry = computed(() => history.value[history.value.length - 1] || null)
  const totalEntries = computed(() => history.value.length)
  const avgDelay = computed(() => {
    if (history.value.length === 0) return '0'
    const sum = history.value.reduce((acc, e) => acc + Number(e.delay || 0), 0)
    return (sum / history.value.length).toFixed(2)
  })
  const serviceLabel = computed(() => {
    if (serverRunning.value && clientRunning.value) return 'Ready'
    if (serverRunning.value || clientRunning.value) return 'Partial'
    return 'Stopped'
  })
  const selectedModel = computed(() => models.value.find((model) => model.id === config.value.server.model) || null)
  function bestBenchmarkForModel(model: ModelEntry, gpuOnly = false) {
    const candidates = [
      model.benchmark,
      benchmarks.value[model.id],
      ...Object.values(model.benchmarks || {}),
    ].filter(Boolean) as ModelBenchmark[]
    const successful = candidates
      .filter((bench) => bench.ok && Number(bench.recognition_seconds || bench.inference_seconds || 0) > 0)
      .filter((bench) => !gpuOnly || bench.actual_gpu)
      .sort((a, b) => Number(a.recognition_seconds || a.inference_seconds || 0) - Number(b.recognition_seconds || b.inference_seconds || 0))
    if (successful.length) return successful[0]
    const relevantFailures = candidates
      .filter((bench) => !gpuOnly || bench.actual_gpu || /cuda|vulkan|dml/.test(bench.acceleration || ''))
      .sort((a, b) => Number(b.updated_at || 0) - Number(a.updated_at || 0))
    return relevantFailures[0] || null
  }
  const accelerationState = computed<AccelerationState>(() => {
    const torch = hardware.value?.torch
    const backend = config.value.server.gpu ? config.value.server.gpu_backend : 'cpu'
    const selected = selectedModel.value
    const isQwen = (selected?.backend || selected?.id || '').toLowerCase().includes('qwen')
    const blocks: string[] = []

    if (!config.value.server.gpu) {
      blocks.push('设置中已关闭 GPU 加速。')
    } else if (config.value.server.gpu_backend === 'cuda') {
      if (!hardware.value?.nvidia_gpu) blocks.push('nvidia-smi 未检测到 NVIDIA GPU。')
      if (!torch?.available) blocks.push(torch?.error || 'PyTorch 不可用。')
      else if (!torch.cuda_available) blocks.push('当前 PyTorch 未启用 CUDA。')
    } else if (config.value.server.gpu_backend === 'vulkan' && isQwen) {
      blocks.push('Qwen safetensors 走 PyTorch；Vulkan 仅适用于 sherpa-onnx 类后端。')
    } else if (config.value.server.gpu_backend === 'dml' && isQwen) {
      blocks.push('当前 Qwen safetensors 后端不使用 DirectML。')
    }

    const cudaReady = Boolean(config.value.server.gpu && config.value.server.gpu_backend === 'cuda' && torch?.cuda_available)
    const vulkanSelected = Boolean(config.value.server.gpu && config.value.server.gpu_backend === 'vulkan')
    const active = Boolean(config.value.server.gpu && blocks.length === 0)
    const label = !config.value.server.gpu
      ? 'CPU'
      : cudaReady
        ? 'CUDA'
        : vulkanSelected && blocks.length === 0
          ? 'Vulkan'
          : 'CPU fallback'
    const detail = blocks.length
      ? blocks[0]
      : active
        ? `${config.value.server.gpu_backend.toUpperCase()} 已用于 ${selected?.name || config.value.server.model}`
        : '已选择 CPU 推理'

    return {
      label,
      detail,
      active,
      backend,
      cudaReady,
      vulkanSelected,
      blocks,
    }
  })
  const accelerationRecommendation = computed<AccelerationRecommendation>(() => {
    const installed = models.value.filter((model) => model.exists)
    const requireGpu = Boolean(config.value.server.gpu_required && !config.value.server.allow_cpu_fallback)
    const benchmarked = installed
      .map((model) => ({ model, benchmark: bestBenchmarkForModel(model, requireGpu) }))
      .filter((entry) => entry.benchmark?.ok && Number(entry.benchmark?.recognition_seconds || 0) > 0)
      .sort((a, b) => Number(a.benchmark?.recognition_seconds || 0) - Number(b.benchmark?.recognition_seconds || 0))
    const daily = installed.find((model) => model.role === 'daily')
    const quality = installed.find((model) => model.role === 'quality')
    const fallback = daily || quality || installed[0] || selectedModel.value
    const recommendedModel = benchmarked[0]?.model || fallback
    const benchmarkSeconds = benchmarked[0]?.benchmark?.recognition_seconds ?? null
    const cudaReady = Boolean(hardware.value?.torch.cuda_available)
    const gpu = cudaReady
    const gpu_backend: AppConfig['server']['gpu_backend'] = cudaReady ? 'cuda' : config.value.server.gpu_backend
    const reason = benchmarked[0]
      ? `已安装${requireGpu ? ' GPU' : ''}模型中最快：${Number(benchmarkSeconds || 0).toFixed(2)}s。`
      : cudaReady
        ? 'CUDA 可用；测试全部已安装模型后可确认最快日用选择。'
        : hardware.value?.recommendation || '测试已安装模型后可选择日用模型。'

    return {
      model: recommendedModel?.id || config.value.server.model,
      modelName: recommendedModel?.name || config.value.server.model,
      gpu,
      gpu_backend,
      reason,
      benchmarkSeconds: benchmarkSeconds == null ? null : Number(benchmarkSeconds),
    }
  })

  async function apiFetch<T = any>(path: string, options?: RequestInit): Promise<T | null> {
    try {
      const res = await fetch(`${API_BASE}${path}`, options)
      const text = await res.text()
      let data: any = {}
      if (text.trim()) {
        try {
          data = JSON.parse(text)
        } catch {
          throw new Error(`${path} returned non-JSON response (${res.status})`)
        }
      }
      if (!res.ok) throw new Error(data?.detail || res.statusText)
      lastError.value = ''
      return data
    } catch (error) {
      const message = error instanceof Error ? error.message : String(error)
      lastError.value = message === 'Failed to fetch'
        ? `无法连接 VoiceType API：${API_BASE}${path}。请确认运行时已启动，或点击“重新启动运行时”。`
        : message
      return null
    }
  }

  async function fetchStatus() {
    const data = await apiFetch<any>('/status')
    if (data) {
      serverRunning.value = Boolean(data.server.running)
      clientRunning.value = Boolean(data.client.running)
      serverPid.value = data.server.pid
      clientPid.value = data.client.pid
      serverManaged.value = Boolean(data.server.managed)
      clientManaged.value = Boolean(data.client.managed)
      serverPortOpen.value = Boolean(data.server.port_open)
      serverConflict.value = Boolean(data.server.conflict)
      clientConflict.value = Boolean(data.client.conflict)
      serverProcessCount.value = Number(data.server.process_count || 0)
      clientProcessCount.value = Number(data.client.process_count || 0)
    } else {
      serverRunning.value = false
      clientRunning.value = false
      serverConflict.value = false
      clientConflict.value = false
      serverProcessCount.value = 0
      clientProcessCount.value = 0
    }
  }

  async function fetchHealth() {
    const data = await apiFetch<any>('/health')
    if (data) {
      recentIssues.value = data.recent_issues || []
      await fetchStatus()
    }
  }

  async function fetchConfig() {
    const data = await apiFetch<AppConfig>('/config')
    if (data) config.value = data
  }

  async function fetchAudioInputDevices() {
    const data = await apiFetch<AudioInputDevicesResponse>('/audio/input-devices')
    if (data) audioInputDevices.value = data
    return data
  }

  async function testAudioInput(deviceIndex = config.value.client.input_device_index) {
    audioInputTesting.value = true
    const data = await apiFetch<AudioInputTestResult>('/audio/test-input', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ device_index: Number(deviceIndex ?? -1), seconds: 3 }),
    })
    if (data) {
      audioInputTest.value = data
      showToast(data.message || (data.has_signal ? '有声音' : '太安静'))
      if (data.audio_wav_base64) {
        playAudioSource(`data:audio/wav;base64,${data.audio_wav_base64}`, 'mic-test')
      }
    }
    audioInputTesting.value = false
    return data
  }

  async function saveConfig() {
    const data = await apiFetch<{ config: AppConfig }>('/config', {
      method: 'PUT',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(config.value),
    })
    if (data?.config) config.value = data.config
    return data
  }

  async function fetchModels() {
    const data = await apiFetch<any>('/models')
    if (data) models.value = data.models || []
  }

  async function fetchHardware() {
    const data = await apiFetch<HardwareInfo>('/hardware')
    if (data) hardware.value = data
  }

  async function fetchBenchmarks() {
    const data = await apiFetch<{ benchmarks: Record<string, ModelBenchmark> }>('/models/benchmark')
    if (data) benchmarks.value = data.benchmarks || {}
  }

  async function runBenchmark(model: string) {
    if (!benchmarkingModels.value.includes(model)) benchmarkingModels.value.push(model)
    const data = await apiFetch<ModelBenchmark>('/models/benchmark', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ model }),
    })
    benchmarkingModels.value = benchmarkingModels.value.filter((item) => item !== model)
    await Promise.all([fetchBenchmarks(), fetchModels()])
    return data
  }

  async function runAllBenchmarks() {
    const targets = models.value.filter((model) => model.exists).map((model) => model.id)
    for (const model of targets) {
      await runBenchmark(model)
    }
    return targets.length
  }

  async function selectModel(model: string) {
    config.value.server.model = model
    config.value.server.model_dir = ''
    await apiFetch('/models/select', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ model }),
    })
    await fetchConfig()
    await fetchModels()
  }

  async function openModelFolder(model: string) {
    return apiFetch(`/models/${encodeURIComponent(model)}/open-folder`, { method: 'POST' })
  }

  async function applyAccelerationRecommendation() {
    const recommendation = accelerationRecommendation.value
    config.value.server.model = recommendation.model
    config.value.server.model_dir = ''
    config.value.server.gpu = recommendation.gpu
    config.value.server.gpu_backend = recommendation.gpu_backend
    await saveConfig()
    await selectModel(recommendation.model)
    await Promise.all([fetchConfig(), fetchModels(), fetchHardware(), fetchBenchmarks()])
  }

  async function startServer() {
    const data = await apiFetch<any>('/server/start', { method: 'POST' })
    if (data?.status === 'external_running') {
      lastError.value = data.message || 'ASR port is already used by an unmanaged service.'
    }
    await fetchStatus()
  }

  async function stopServer() {
    await apiFetch('/server/stop', { method: 'POST' })
    await fetchStatus()
  }

  async function startClient() {
    await apiFetch('/client/start', { method: 'POST' })
    await fetchStatus()
  }

  async function stopClient() {
    await apiFetch('/client/stop', { method: 'POST' })
    await fetchStatus()
  }

  async function restartClient() {
    await stopClient()
    await startClient()
  }

  async function tauriInvoke<T = any>(command: string): Promise<T | null> {
    const tauriWindow = window as any
    if (!tauriWindow.__TAURI_INTERNALS__) return null
    try {
      const mod = await import('@tauri-apps/api/core')
      return await mod.invoke<T>(command)
    } catch (error) {
      lastError.value = error instanceof Error ? error.message : String(error)
      return null
    }
  }

  async function fetchRuntimeDiagnostics() {
    const data = await tauriInvoke<string>('runtime_diagnostics')
    if (data) runtimeDiagnostics.value = data
    return data
  }

  async function restartRuntime() {
    runtimeRestarting.value = true
    const data = await tauriInvoke<string>('restart_runtime')
    if (data) showToast('正在重启运行时')
    await new Promise((resolve) => setTimeout(resolve, 2200))
    await Promise.all([fetchStatus(), fetchHealth(), fetchConfig(), fetchAudioInputDevices()])
    runtimeRestarting.value = false
    return data
  }

  async function startAll() {
    await apiFetch('/start-all', { method: 'POST' })
    await fetchStatus()
  }

  async function stopAll() {
    await apiFetch('/stop-all', { method: 'POST' })
    await fetchStatus()
  }

  async function fetchHistory() {
    const data = await apiFetch<any>('/history?limit=200')
    if (data) history.value = data.entries || []
  }

  async function clearHistory() {
    await apiFetch('/history/clear', { method: 'POST' })
    history.value = []
  }

  async function deleteHistoryEntry(taskId: string) {
    await apiFetch(`/history/${encodeURIComponent(taskId)}`, { method: 'DELETE' })
    history.value = history.value.filter((entry) => entry.task_id !== taskId)
  }

  async function addErrorMark(text: string, markedText: string) {
    await apiFetch('/error-mark', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ text, marked_text: markedText }),
    })
    await fetchErrorMarks()
  }

  async function fetchErrorMarks() {
    const data = await apiFetch<any>('/error-marks')
    if (data) errorMarks.value = data.marks || []
  }

  async function fetchStats() {
    const data = await apiFetch<any>('/stats')
    if (data) topWords.value = data.top_words || []
  }

  async function fetchLogs() {
    const data = await apiFetch<any>('/logs/recent?lines=160')
    if (data) logs.value = data.logs || []
  }

  async function fetchHotword(name = selectedHotword.value) {
    selectedHotword.value = name
    const data = await apiFetch<any>(`/hotwords/${encodeURIComponent(name)}`)
    if (data) hotwordContent.value[name] = data.content || ''
  }

  async function saveHotword(name = selectedHotword.value) {
    await apiFetch(`/hotwords/${encodeURIComponent(name)}`, {
      method: 'PUT',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ content: hotwordContent.value[name] || '' }),
    })
    await apiFetch('/reload-hotwords', { method: 'POST' })
  }

  async function fetchFfmpegStatus() {
    const data = await apiFetch<FfmpegStatus>('/ffmpeg/status')
    if (data) ffmpeg.value = data
  }

  async function fetchLlmConfig() {
    const data = await apiFetch<LlmConfig>('/llm/config')
    if (data) llmConfig.value = data
  }

  async function saveLlmConfig() {
    const data = await apiFetch<{ config: LlmConfig }>('/llm/config', {
      method: 'PUT',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(llmConfig.value),
    })
    if (data?.config) llmConfig.value = data.config
  }

  async function fetchTranscriptions() {
    const data = await apiFetch<{ tasks: TranscriptionTask[] }>('/transcriptions')
    if (data) transcriptions.value = data.tasks || []
  }

  async function createTranscription(payload: Record<string, any>) {
    const data = await apiFetch<TranscriptionTask>('/transcriptions', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(payload),
    })
    await fetchTranscriptions()
    return data
  }

  async function uploadTranscription(files: File[], payload: Record<string, any>) {
    try {
      const form = new FormData()
      files.forEach((file) => form.append('files', file))
      form.append('options', JSON.stringify(payload))
      const res = await fetch(`${API_BASE}/transcriptions/upload`, {
        method: 'POST',
        body: form,
      })
      const text = await res.text()
      const data = text ? JSON.parse(text) : null
      if (!res.ok) throw new Error(data?.detail || res.statusText)
      lastError.value = ''
      await fetchTranscriptions()
      return data as TranscriptionTask
    } catch (error) {
      lastError.value = error instanceof Error ? error.message : String(error)
      return null
    }
  }

  async function cancelTranscription(taskId: string) {
    await apiFetch(`/transcriptions/${encodeURIComponent(taskId)}/cancel`, { method: 'POST' })
    await fetchTranscriptions()
  }

  function connectRecognition() {
    if (ws.current && ws.current.readyState <= WebSocket.OPEN) return
    ws.current = new WebSocket(WS_RECOGNITION_URL)

    ws.current.onopen = () => {
      wsConnected.value = true
      currentPartial.value = ''
    }

    ws.current.onmessage = (event) => {
      const data = JSON.parse(event.data)
      if (data.type === 'result') {
        currentPartial.value = ''
        const duration = Number(data.duration_seconds ?? data.delay ?? ((data.time_complete || 0) - (data.time_submit || 0)))
        const entry: HistoryEntry = {
          text: data.text || '',
          task_id: data.task_id || `${Date.now()}`,
          timestamp: data.timestamp || Date.now() / 1000,
          delay: duration,
          duration_seconds: duration,
          audio_path: data.audio_path || '',
          transcript_path: data.transcript_path || '',
          model: data.model || '',
        }
        if (!history.value.some((item) => item.task_id === entry.task_id)) {
          history.value.push(entry)
        }
        fetchStats()
      } else if (data.type === 'partial') {
        currentPartial.value = data.text || ''
      } else if (data.type === 'disconnected') {
        wsConnected.value = false
      }
    }

    ws.current.onclose = () => {
      wsConnected.value = false
      ws.current = null
    }

    ws.current.onerror = () => {
      wsConnected.value = false
    }
  }

  function disconnectRecognition() {
    ws.current?.close()
    ws.current = null
    wsConnected.value = false
  }

  function showToast(message: string) {
    toastMessage.value = message
    if (toastTimer) clearTimeout(toastTimer)
    toastTimer = setTimeout(() => {
      toastMessage.value = ''
    }, 1200)
  }

  async function copyToClipboard(text: string) {
    if (!text) return false
    try {
      await navigator.clipboard?.writeText(text)
      showToast('已复制')
      return true
    } catch (error) {
      lastError.value = error instanceof Error ? error.message : String(error)
      showToast('复制失败')
      return false
    }
  }

  function stopAudio() {
    if (activeAudio) {
      activeAudio.pause()
      activeAudio.currentTime = 0
      activeAudio = null
    }
    playingTaskId.value = ''
  }

  function playAudioSource(source: string, id: string) {
    if (playingTaskId.value === id) {
      stopAudio()
      return
    }
    stopAudio()
    activeAudio = new Audio(source)
    playingTaskId.value = id
    activeAudio.onended = () => {
      if (playingTaskId.value === id) playingTaskId.value = ''
      activeAudio = null
    }
    activeAudio.onerror = () => {
      showToast('播放失败')
      if (playingTaskId.value === id) playingTaskId.value = ''
      activeAudio = null
    }
    activeAudio.play().catch((error) => {
      lastError.value = error instanceof Error ? error.message : String(error)
      showToast('播放失败')
      if (playingTaskId.value === id) playingTaskId.value = ''
      activeAudio = null
    })
  }

  function playHistoryAudio(entry: HistoryEntry) {
    if (!entry.audio_path) {
      showToast('没有录音文件')
      return
    }
    playAudioSource(`${API_BASE}/history/${encodeURIComponent(entry.task_id)}/audio`, entry.task_id)
  }

  return {
    serverRunning, clientRunning, serverPid, clientPid, serverManaged, clientManaged,
    serverPortOpen, serverConflict, clientConflict, serverProcessCount, clientProcessCount,
    history, errorMarks, wsConnected, currentPartial, topWords,
    config, models, logs, recentIssues, hotwordContent, selectedHotword, toastMessage,
    ffmpeg, llmConfig, transcriptions, audioInputDevices, audioInputTest, audioInputTesting, playingTaskId, runtimeDiagnostics, runtimeRestarting, hardware, benchmarks, benchmarkingModels, lastError,
    apiBase: API_BASE,
    latestEntry, totalEntries, avgDelay, serviceLabel, selectedModel, accelerationState, accelerationRecommendation,
    fetchStatus, fetchHealth, fetchConfig, fetchAudioInputDevices, testAudioInput, saveConfig, fetchModels, fetchHardware, fetchBenchmarks, runBenchmark, runAllBenchmarks, selectModel, openModelFolder, applyAccelerationRecommendation,
    startServer, stopServer, startClient, stopClient, restartClient, startAll, stopAll,
    fetchRuntimeDiagnostics, restartRuntime,
    fetchHistory, clearHistory, deleteHistoryEntry, addErrorMark, fetchErrorMarks,
    fetchStats, fetchLogs, fetchHotword, saveHotword,
    fetchFfmpegStatus, fetchLlmConfig, saveLlmConfig,
    fetchTranscriptions, createTranscription, uploadTranscription, cancelTranscription,
    connectRecognition, disconnectRecognition, copyToClipboard, showToast, playHistoryAudio, stopAudio,
  }
})

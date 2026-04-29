import { defineStore } from 'pinia'
import { computed, ref } from 'vue'

export interface HistoryEntry {
  text: string
  task_id: string
  timestamp: number
  delay: number
  audio_path?: string
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
    gpu_backend: 'vulkan' | 'dml' | 'cuda'
  }
  client: {
    server_host: string
    server_port: number
    shortcut_key: string
    output_mode: 'clipboard' | 'keyboard' | 'hybrid'
    save_audio: boolean
    audio_dir: string
    hotword_files: string[]
    notification_enabled: boolean
    notification_sound: boolean
  }
}

export interface ModelEntry {
  id: string
  name: string
  path: string
  exists: boolean
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

const API_BASE = '/api'

const defaultConfig: AppConfig = {
  server: {
    host: '0.0.0.0',
    port: 52341,
    model: 'qwen3-asr-1.7b',
    model_dir: '',
    gpu: true,
    gpu_backend: 'cuda',
  },
  client: {
    server_host: '127.0.0.1',
    server_port: 52341,
    shortcut_key: 'caps_lock',
    output_mode: 'clipboard',
    save_audio: true,
    audio_dir: '',
    hotword_files: ['hot-zh.txt', 'hot-en.txt', 'hot-rule.txt'],
    notification_enabled: true,
    notification_sound: true,
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
  const history = ref<HistoryEntry[]>([])
  const errorMarks = ref<ErrorMark[]>([])
  const wsConnected = ref(false)
  const currentPartial = ref('')
  const topWords = ref<{ word: string; count: number }[]>([])
  const config = ref<AppConfig>(structuredClone(defaultConfig))
  const models = ref<ModelEntry[]>([])
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
  const lastError = ref('')
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
      lastError.value = error instanceof Error ? error.message : String(error)
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
    } else {
      serverRunning.value = false
      clientRunning.value = false
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
    const protocol = window.location.protocol === 'https:' ? 'wss' : 'ws'
    ws.current = new WebSocket(`${protocol}://${window.location.host}/ws/recognition`)

    ws.current.onopen = () => {
      wsConnected.value = true
      currentPartial.value = ''
    }

    ws.current.onmessage = (event) => {
      const data = JSON.parse(event.data)
      if (data.type === 'result') {
        currentPartial.value = ''
        const entry: HistoryEntry = {
          text: data.text || '',
          task_id: data.task_id || `${Date.now()}`,
          timestamp: data.timestamp || Date.now() / 1000,
          delay: Number(data.delay ?? ((data.time_complete || 0) - (data.time_submit || 0))),
          audio_path: data.audio_path || '',
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

  function copyToClipboard(text: string) {
    navigator.clipboard?.writeText(text)
  }

  return {
    serverRunning, clientRunning, serverPid, clientPid, serverManaged, clientManaged,
    serverPortOpen, history, errorMarks, wsConnected, currentPartial, topWords,
    config, models, logs, recentIssues, hotwordContent, selectedHotword,
    ffmpeg, llmConfig, transcriptions, lastError,
    latestEntry, totalEntries, avgDelay, serviceLabel,
    fetchStatus, fetchHealth, fetchConfig, saveConfig, fetchModels, selectModel,
    startServer, stopServer, startClient, stopClient, startAll, stopAll,
    fetchHistory, clearHistory, deleteHistoryEntry, addErrorMark, fetchErrorMarks,
    fetchStats, fetchLogs, fetchHotword, saveHotword,
    fetchFfmpegStatus, fetchLlmConfig, saveLlmConfig,
    fetchTranscriptions, createTranscription, uploadTranscription, cancelTranscription,
    connectRecognition, disconnectRecognition, copyToClipboard,
  }
})

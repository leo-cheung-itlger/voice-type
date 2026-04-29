import { defineStore } from 'pinia'
import { ref, computed } from 'vue'

export interface HistoryEntry {
  text: string
  task_id: string
  timestamp: number
  delay: number
  audio_path?: string
  marked?: boolean
  marked_words_text?: string
}

export interface ErrorMark {
  text: string
  marked_text: string
  timestamp: number
}

const API_BASE = '/api'

export const useAppStore = defineStore('app', () => {
  const serverRunning = ref(false)
  const clientRunning = ref(false)
  const serverPid = ref<number | null>(null)
  const clientPid = ref<number | null>(null)
  const history = ref<HistoryEntry[]>([])
  const errorMarks = ref<ErrorMark[]>([])
  const wsConnected = ref(false)
  const currentPartial = ref('')
  const topWords = ref<{ word: string; count: number }[]>([])
  const outputMode = ref<'clipboard' | 'keyboard' | 'hybrid'>('clipboard')

  const totalEntries = computed(() => history.value.length)
  const avgDelay = computed(() => {
    if (history.value.length === 0) return '0'
    const sum = history.value.reduce((acc, e) => acc + e.delay, 0)
    return (sum / history.value.length).toFixed(2)
  })

  async function apiFetch(path: string, options?: RequestInit) {
    try {
      const res = await fetch(`${API_BASE}${path}`, options)
      return await res.json()
    } catch {
      return null
    }
  }

  async function fetchStatus() {
    const data = await apiFetch('/status')
    if (data) {
      serverRunning.value = data.server.running
      clientRunning.value = data.client.running
      serverPid.value = data.server.pid
      clientPid.value = data.client.pid
    } else {
      serverRunning.value = false
      clientRunning.value = false
    }
  }

  async function startServer() {
    await apiFetch('/server/start', { method: 'POST' })
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
    const data = await apiFetch('/history?limit=200')
    if (data) history.value = data.entries || []
  }

  async function clearHistory() {
    await apiFetch('/history/clear', { method: 'POST' })
    history.value = []
  }

  async function addErrorMark(text: string, markedText: string) {
    await apiFetch('/error-mark', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ text, marked_text: markedText }),
    })
  }

  async function fetchErrorMarks() {
    const data = await apiFetch('/error-marks')
    if (data) errorMarks.value = data.marks || []
  }

  async function fetchStats() {
    const data = await apiFetch('/stats')
    if (data) topWords.value = data.top_words || []
  }

  function copyToClipboard(text: string) {
    navigator.clipboard.writeText(text)
  }

  return {
    serverRunning, clientRunning, serverPid, clientPid,
    history, errorMarks, wsConnected, currentPartial,
    topWords, outputMode, totalEntries, avgDelay,
    fetchStatus, startServer, stopServer, startClient, stopClient,
    startAll, stopAll, fetchHistory, clearHistory,
    addErrorMark, fetchErrorMarks, fetchStats, copyToClipboard,
  }
})

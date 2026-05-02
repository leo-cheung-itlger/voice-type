<template>
  <main class="shell">
    <header class="topbar">
      <div>
        <div class="brand">VoiceType</div>
        <div class="subline">{{ store.serviceLabel }} · {{ store.config.server.model }}</div>
      </div>
      <div class="status-pills" aria-label="service status">
        <span class="pill" :class="{ on: store.serverRunning }">ASR</span>
        <span class="pill" :class="{ on: store.clientRunning }">Client</span>
        <span class="pill" :class="{ on: store.wsConnected }">Live</span>
      </div>
    </header>

    <section v-if="store.lastError" class="error-strip">
      <div>
        <strong>运行时连接异常</strong>
        <p>{{ store.lastError }}</p>
        <small>API: {{ store.apiBase }}</small>
        <pre v-if="store.runtimeDiagnostics">{{ store.runtimeDiagnostics }}</pre>
      </div>
      <div class="error-actions">
        <button class="btn btn-small btn-primary" :disabled="store.runtimeRestarting" @click="store.restartRuntime()">
          {{ store.runtimeRestarting ? '重启中' : '重新启动运行时' }}
        </button>
        <button class="btn btn-small btn-ghost" @click="store.fetchRuntimeDiagnostics()">诊断</button>
      </div>
    </section>

    <section class="workspace">
      <router-view />
    </section>

    <nav class="tabbar">
      <router-link to="/" class="tab">控制</router-link>
      <router-link to="/transcriptions" class="tab">转录</router-link>
      <router-link to="/history" class="tab">历史</router-link>
      <router-link to="/hotwords" class="tab">热词</router-link>
      <router-link to="/stats" class="tab">统计</router-link>
      <router-link to="/settings" class="tab">设置</router-link>
    </nav>

    <div v-if="store.toastMessage" class="toast">{{ store.toastMessage }}</div>
  </main>
</template>

<script setup lang="ts">
import { onMounted, onUnmounted } from 'vue'
import { useAppStore } from './stores/app'

const store = useAppStore()
let timer: ReturnType<typeof setInterval> | null = null
let unlistenSingleInstance: (() => void) | null = null
let unlistenRuntimeToast: (() => void) | null = null

async function wireTauriEvents() {
  const tauriWindow = window as any
  if (!tauriWindow.__TAURI_INTERNALS__) return
  const mod = await import('@tauri-apps/api/event')
  unlistenSingleInstance = await mod.listen('single-instance', () => {
    store.showToast('VoiceType 已在运行')
  })
  unlistenRuntimeToast = await mod.listen<string>('runtime-toast', (event) => {
    store.showToast(event.payload)
    if (event.payload.includes('缺失') || event.payload.includes('失败')) {
      store.lastError = event.payload
      store.fetchRuntimeDiagnostics()
    }
  })
}

onMounted(async () => {
  await wireTauriEvents()
  await Promise.all([
    store.fetchConfig(),
    store.fetchStatus(),
    store.fetchHealth(),
    store.fetchHistory(),
    store.fetchStats(),
    store.fetchModels(),
    store.fetchHardware(),
    store.fetchAudioInputDevices(),
  ])
  store.connectRecognition()
  timer = setInterval(() => {
    store.fetchStatus()
    store.fetchHealth()
  }, 5000)
})

onUnmounted(() => {
  if (timer) clearInterval(timer)
  unlistenSingleInstance?.()
  unlistenRuntimeToast?.()
  store.disconnectRecognition()
})
</script>

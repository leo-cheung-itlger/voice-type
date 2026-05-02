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

    <div v-if="startupVisible" class="startup-overlay">
      <div class="startup-card">
        <div class="startup-spinner" aria-hidden="true"></div>
        <div>
          <h1>VoiceType 正在启动，请耐心等待</h1>
          <p>{{ startupStage }}</p>
          <small>{{ startupDetail }}</small>
        </div>
        <button
          v-if="startupFailed"
          class="btn btn-small btn-primary"
          :disabled="store.runtimeRestarting"
          @click="restartStartupRuntime"
        >
          {{ store.runtimeRestarting ? '重启中' : '重新启动运行时' }}
        </button>
      </div>
    </div>

    <div v-if="store.toastMessage" class="toast">{{ store.toastMessage }}</div>
  </main>
</template>

<script setup lang="ts">
import { computed, onMounted, onUnmounted, ref } from 'vue'
import { useAppStore } from './stores/app'

const store = useAppStore()
let timer: ReturnType<typeof setInterval> | null = null
let unlistenSingleInstance: (() => void) | null = null
let unlistenRuntimeToast: (() => void) | null = null
const startupVisible = ref(true)
const startupStage = ref('检查运行时脚本')
const startupDetail = ref('正在连接本地 VoiceType API')
const startupFailed = computed(() => Boolean(store.lastError && startupVisible.value))

async function wireTauriEvents() {
  const tauriWindow = window as any
  if (!tauriWindow.__TAURI_INTERNALS__) return
  const mod = await import('@tauri-apps/api/event')
  unlistenSingleInstance = await mod.listen('single-instance', () => {
    store.showToast('VoiceType 已在运行')
  })
  unlistenRuntimeToast = await mod.listen<string>('runtime-toast', (event) => {
    store.showToast(event.payload)
    startupStage.value = event.payload.includes('完成') ? '完成' : event.payload
    startupDetail.value = '桌面壳正在等待本地运行时就绪'
    if (event.payload.includes('缺失') || event.payload.includes('失败')) {
      store.lastError = event.payload
      store.fetchRuntimeDiagnostics()
    }
  })
}

function updateStartupState() {
  if (store.lastError) {
    startupVisible.value = true
    startupStage.value = '启动失败'
    startupDetail.value = store.lastError
    return
  }
  if (!store.serverRunning) {
    startupVisible.value = true
    startupStage.value = '启动 API 和 ASR 服务'
    startupDetail.value = '模型加载中，暂不可录音'
    return
  }
  if (!store.clientRunning) {
    startupVisible.value = true
    startupStage.value = '启动录音客户端'
    startupDetail.value = '正在加载快捷键监听和麦克风配置'
    return
  }
  startupStage.value = '完成'
  startupDetail.value = '本地运行时已就绪'
  window.setTimeout(() => {
    if (!store.lastError && store.serverRunning && store.clientRunning) {
      startupVisible.value = false
    }
  }, 700)
}

async function restartStartupRuntime() {
  startupVisible.value = true
  startupStage.value = '重新启动运行时'
  startupDetail.value = '正在清理旧进程并重新拉起 API/ASR/client'
  await store.restartRuntime()
  updateStartupState()
}

onMounted(async () => {
  await wireTauriEvents()
  startupStage.value = '连接本地 API'
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
  updateStartupState()
  store.connectRecognition()
  timer = setInterval(() => {
    Promise.all([store.fetchStatus(), store.fetchHealth()]).then(updateStartupState)
  }, 5000)
})

onUnmounted(() => {
  if (timer) clearInterval(timer)
  unlistenSingleInstance?.()
  unlistenRuntimeToast?.()
  store.disconnectRecognition()
})
</script>

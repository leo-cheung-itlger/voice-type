<template>
  <main class="shell">
    <header class="topbar">
      <div>
        <div class="brand-row">
          <div class="brand">VoiceType</div>
          <span class="version-badge">{{ store.appVersionLabel }}</span>
        </div>
        <button class="model-switch" aria-label="切换识别模型" @click="openModelSettings">
          <span>{{ store.activeModelLabel }}</span>
          <svg viewBox="0 0 16 16" aria-hidden="true"><path d="m5 3 5 5-5 5" /></svg>
        </button>
      </div>
      <div class="status-pills" role="status" aria-label="语音输入状态">
        <span class="pill" :class="{ on: store.serverRunning && store.clientRunning && store.wsConnected }">{{ store.serviceLabel }}</span>
      </div>
    </header>

    <section v-if="store.lastError && !startupVisible" class="error-strip">
      <div>
        <strong>操作未完成</strong>
        <p>{{ store.lastError }}</p>

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
import { computed, nextTick, onMounted, onUnmounted, ref } from 'vue'
import { useRouter } from 'vue-router'
import { useAppStore } from './stores/app'

const store = useAppStore()
const router = useRouter()
let timer: ReturnType<typeof setInterval> | null = null
let refreshing = false
let unlistenSingleInstance: (() => void) | null = null
let unlistenRuntimeToast: (() => void) | null = null
const startupVisible = ref(true)
const startupStage = ref('检查运行时脚本')
const startupDetail = ref('正在连接本地 VoiceType API')
const startupStartedAt = ref(Date.now())
const startupErrorDelayMs = 45000
const startupFailed = computed(() => Boolean(store.lastError && startupVisible.value))

async function openModelSettings() {
  await router.push('/settings#models')
  await nextTick()
  const section = document.getElementById('models')
  section?.scrollIntoView({ block: 'start' })
  section?.focus({ preventScroll: true })
}

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
  if (!startupVisible.value) return
  const withinStartupGrace = Date.now() - startupStartedAt.value < startupErrorDelayMs
  if (withinStartupGrace && store.lastError.startsWith('无法连接 VoiceType API')) {
    store.lastError = ''
  }
  if (store.lastError) {
    startupVisible.value = true
    startupStage.value = '启动失败'
    startupDetail.value = store.lastError
    return
  }
  if (store.apiReady) {
    startupVisible.value = false
  } else {
    startupStage.value = '连接本地服务'
    startupDetail.value = '首次启动无需先下载模型'
  }
}

async function restartStartupRuntime() {
  startupStartedAt.value = Date.now()
  store.suppressConnectionErrors(startupErrorDelayMs)
  startupVisible.value = true
  startupStage.value = '重新启动运行时'
  startupDetail.value = '正在清理旧进程并重新拉起 API/ASR/client'
  await store.restartRuntime()
  updateStartupState()
}

onMounted(async () => {
  await wireTauriEvents()
  startupStartedAt.value = Date.now()
  store.suppressConnectionErrors(startupErrorDelayMs)
  startupStage.value = '连接本地 API'
  await Promise.all([
    store.fetchConfig(),
    store.fetchHealth(),
    store.fetchHistory(),
    store.fetchModels(),
    store.fetchHardware(),
  ])
  updateStartupState()
  store.connectRecognition()
  timer = setInterval(async () => {
    if (refreshing) return
    refreshing = true
    try {
      await store.fetchHealth(8000)
      store.connectRecognition()
      updateStartupState()
    } finally {
      refreshing = false
    }
  }, 5000)
})

onUnmounted(() => {
  if (timer) clearInterval(timer)
  unlistenSingleInstance?.()
  unlistenRuntimeToast?.()
  store.disconnectRecognition()
})
</script>

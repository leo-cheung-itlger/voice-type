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
      {{ store.lastError }}
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
  </main>
</template>

<script setup lang="ts">
import { onMounted, onUnmounted } from 'vue'
import { useAppStore } from './stores/app'

const store = useAppStore()
let timer: ReturnType<typeof setInterval> | null = null

onMounted(async () => {
  await Promise.all([
    store.fetchConfig(),
    store.fetchStatus(),
    store.fetchHealth(),
    store.fetchHistory(),
    store.fetchStats(),
    store.fetchModels(),
  ])
  store.connectRecognition()
  timer = setInterval(() => {
    store.fetchStatus()
    store.fetchHealth()
  }, 5000)
})

onUnmounted(() => {
  if (timer) clearInterval(timer)
  store.disconnectRecognition()
})
</script>

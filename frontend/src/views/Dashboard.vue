<template>
  <div class="dashboard">
    <div class="status-panel">
      <div class="card status-card" :class="{ running: store.serverRunning }">
        <span :class="store.serverRunning ? 'dot dot-green' : 'dot dot-red'"></span>
        <div class="status-info">
          <h3>ASR 服务端</h3>
          <p>{{ store.serverRunning ? `运行中 (PID: ${store.serverPid})` : '未启动' }}</p>
        </div>
        <button v-if="!store.serverRunning" @click="store.startServer()" class="btn btn-success">启动</button>
        <button v-else @click="store.stopServer()" class="btn btn-danger">停止</button>
      </div>

      <div class="card status-card" :class="{ running: store.clientRunning }">
        <span :class="store.clientRunning ? 'dot dot-green' : 'dot dot-red'"></span>
        <div class="status-info">
          <h3>客户端</h3>
          <p>{{ store.clientRunning ? `运行中 (PID: ${store.clientPid})` : '未启动' }}</p>
        </div>
        <button v-if="!store.clientRunning" @click="store.startClient()" class="btn btn-success">启动</button>
        <button v-else @click="store.stopClient()" class="btn btn-danger">停止</button>
      </div>
    </div>

    <div class="quick-actions">
      <button @click="store.startAll()" class="btn btn-primary" :disabled="store.serverRunning && store.clientRunning">
        一键启动全部
      </button>
      <button @click="store.stopAll()" class="btn btn-danger" :disabled="!store.serverRunning && !store.clientRunning">
        一键停止全部
      </button>
    </div>

    <div class="stats-row">
      <div class="card stat-item">
        <span class="stat-value">{{ store.totalEntries }}</span>
        <span class="stat-label">识别次数</span>
      </div>
      <div class="card stat-item">
        <span class="stat-value">{{ store.avgDelay }}s</span>
        <span class="stat-label">平均延迟</span>
      </div>
      <div class="card stat-item">
        <span class="stat-value">{{ store.wsConnected ? '已连接' : '未连接' }}</span>
        <span class="stat-label">WebSocket</span>
      </div>
    </div>

    <div class="card realtime-panel">
      <h3>实时识别</h3>
      <div class="realtime-text">
        <span v-if="store.currentPartial" class="partial">{{ store.currentPartial }}</span>
        <span v-else class="placeholder">等待语音输入...</span>
      </div>
    </div>

    <div class="card recent-panel">
      <h3>最近识别</h3>
      <div class="recent-list">
        <div v-for="entry in store.history.slice(-5).reverse()" :key="entry.task_id" class="recent-item">
          <span class="recent-text">{{ entry.text }}</span>
          <span class="recent-delay">{{ entry.delay.toFixed(2) }}s</span>
          <button @click="store.copyToClipboard(entry.text)" class="btn btn-ghost btn-small">复制</button>
        </div>
        <div v-if="store.history.length === 0" class="empty">暂无记录</div>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { onMounted, onUnmounted } from 'vue'
import { useAppStore } from '../stores/app'

const store = useAppStore()
let timer: ReturnType<typeof setInterval> | null = null

onMounted(() => {
  store.fetchStatus()
  store.fetchHistory()
  timer = setInterval(() => store.fetchStatus(), 5000)
})

onUnmounted(() => {
  if (timer) clearInterval(timer)
})
</script>

<style scoped>
.dashboard { padding: 24px; max-width: 900px; margin: 0 auto; }
.status-panel { display: flex; gap: 16px; margin-bottom: 16px; }
.status-card { display: flex; align-items: center; gap: 12px; flex: 1; }
.status-card.running { border-color: var(--accent-green); }
.status-info { flex: 1; }
.status-info h3 { font-size: 15px; margin-bottom: 2px; }
.status-info p { font-size: 13px; color: var(--text-secondary); }
.quick-actions { display: flex; gap: 12px; margin-bottom: 16px; }
.quick-actions .btn { flex: 1; justify-content: center; }
.stats-row { display: flex; gap: 16px; margin-bottom: 16px; }
.stat-item { flex: 1; text-align: center; }
.stat-value { display: block; font-size: 24px; font-weight: 700; color: var(--accent-blue); }
.stat-label { display: block; font-size: 12px; color: var(--text-secondary); margin-top: 4px; }
.realtime-panel { margin-bottom: 16px; }
.realtime-panel h3 { margin-bottom: 12px; font-size: 15px; }
.realtime-text { min-height: 40px; padding: 12px; border-radius: 8px; background: var(--bg-base); font-size: 16px; }
.partial { color: var(--accent-yellow); }
.placeholder { color: var(--text-muted); }
.recent-panel h3 { margin-bottom: 12px; font-size: 15px; }
.recent-item { display: flex; align-items: center; gap: 8px; padding: 8px 12px; border-radius: 8px; margin-bottom: 4px; background: var(--bg-base); }
.recent-text { flex: 1; font-size: 14px; }
.recent-delay { color: var(--text-secondary); font-size: 12px; }
.empty { color: var(--text-muted); text-align: center; padding: 20px; }
</style>

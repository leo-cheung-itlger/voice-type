<template>
  <div class="view dashboard-view">
    <section class="section hero">
      <div class="hero-main">
        <span class="label">最新识别</span>
        <p v-if="store.currentPartial" class="live-text partial">{{ store.currentPartial }}</p>
        <p v-else-if="store.latestEntry" class="live-text">{{ store.latestEntry.text }}</p>
        <p v-else class="live-text muted">等待按键录音</p>
      </div>
      <div class="hero-actions">
        <button class="btn btn-primary" @click="store.startAll()" :disabled="store.serverRunning && store.clientRunning">启动</button>
        <button class="btn btn-ghost" @click="store.stopAll()" :disabled="!store.serverRunning && !store.clientRunning">停止</button>
      </div>
    </section>

    <section class="section">
      <div class="section-title">
        <span>服务</span>
        <button class="btn btn-small btn-ghost" @click="refresh">刷新</button>
      </div>
      <div class="panel">
        <div class="row">
          <div>
            <div class="value">ASR 服务端</div>
            <div class="label">{{ serverLabel }}</div>
          </div>
          <button
            class="btn btn-small"
            :class="store.serverRunning && store.serverManaged ? 'btn-danger' : 'btn-primary'"
            :disabled="store.serverRunning && !store.serverManaged"
            @click="toggleServer"
          >
            {{ serverButtonLabel }}
          </button>
        </div>
        <div class="row">
          <div>
            <div class="value">录音客户端</div>
            <div class="label">{{ store.clientRunning ? `PID ${store.clientPid || '-'}` : store.config.client.shortcut_key }}</div>
          </div>
          <button class="btn btn-small" :class="store.clientRunning ? 'btn-danger' : 'btn-primary'" @click="toggleClient">
            {{ store.clientRunning ? '停止' : '启动' }}
          </button>
        </div>
        <div class="row">
          <div>
            <div class="value">控制台连接</div>
            <div class="label">{{ store.wsConnected ? '正在监听识别结果' : '未连接到 API WebSocket' }}</div>
          </div>
          <button class="btn btn-small btn-ghost" @click="store.connectRecognition()">重连</button>
        </div>
      </div>
    </section>

    <section class="section quick-stats">
      <div>
        <strong>{{ store.totalEntries }}</strong>
        <span>次数</span>
      </div>
      <div>
        <strong>{{ store.avgDelay }}s</strong>
        <span>平均</span>
      </div>
      <div>
        <strong>{{ store.config.client.output_mode }}</strong>
        <span>输出</span>
      </div>
    </section>

    <section class="section">
      <div class="section-title">
        <span>最近</span>
        <button v-if="store.latestEntry" class="btn btn-small btn-ghost" @click="store.copyToClipboard(store.latestEntry.text)">复制最新</button>
      </div>
      <div class="panel recent-list">
        <div v-for="entry in recentEntries" :key="entry.task_id" class="recent-item">
          <p>{{ entry.text }}</p>
          <span>{{ entry.delay.toFixed(2) }}s</span>
        </div>
        <div v-if="recentEntries.length === 0" class="empty">暂无识别记录</div>
      </div>
    </section>

    <section v-if="store.recentIssues.length" class="section">
      <div class="section-title"><span>最近问题</span></div>
      <div class="panel issue-list">
        <div v-for="(issue, i) in store.recentIssues.slice(-3)" :key="i" class="issue-line">{{ issue.line }}</div>
      </div>
    </section>
  </div>
</template>

<script setup lang="ts">
import { computed } from 'vue'
import { useAppStore } from '../stores/app'

const store = useAppStore()
const recentEntries = computed(() => [...store.history].slice(-4).reverse())
const serverLabel = computed(() => {
  if (store.serverRunning && store.serverManaged) return `托管运行 PID ${store.serverPid || '-'}`
  if (store.serverRunning && !store.serverManaged) return `外部服务占用端口 ${store.config.server.port}`
  return '等待启动'
})
const serverButtonLabel = computed(() => {
  if (store.serverRunning && store.serverManaged) return '停止'
  if (store.serverRunning && !store.serverManaged) return '外部'
  return '启动'
})

async function refresh() {
  await Promise.all([store.fetchStatus(), store.fetchHealth(), store.fetchHistory()])
}

async function toggleServer() {
  if (store.serverRunning && !store.serverManaged) return
  if (store.serverRunning) await store.stopServer()
  else await store.startServer()
}

async function toggleClient() {
  if (store.clientRunning) await store.stopClient()
  else await store.startClient()
}
</script>

<style scoped>
.hero {
  display: grid;
  gap: 14px;
  padding: 16px;
  border: 1px solid rgba(125, 220, 155, 0.24);
  border-radius: 14px;
  background: linear-gradient(180deg, rgba(125, 220, 155, 0.08), rgba(24, 27, 25, 0.9));
}

.live-text {
  min-height: 78px;
  max-height: 150px;
  overflow-y: auto;
  margin-top: 8px;
  font-size: 24px;
  line-height: 1.35;
  word-break: break-word;
}

.partial {
  color: var(--warn);
}

.hero-actions {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 8px;
}

.quick-stats {
  display: grid;
  grid-template-columns: repeat(3, 1fr);
  gap: 8px;
}

.quick-stats div {
  padding: 12px;
  border: 1px solid var(--line);
  border-radius: 12px;
  background: var(--panel);
}

.quick-stats strong,
.quick-stats span {
  display: block;
}

.quick-stats strong {
  overflow: hidden;
  font-size: 18px;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.quick-stats span {
  margin-top: 3px;
  color: var(--muted);
  font-size: 12px;
}

.recent-list {
  overflow: hidden;
}

.recent-item {
  display: grid;
  grid-template-columns: 1fr auto;
  gap: 10px;
  padding: 11px 13px;
  border-bottom: 1px solid var(--line);
}

.recent-item:last-child {
  border-bottom: 0;
}

.recent-item p {
  overflow: hidden;
  font-size: 14px;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.recent-item span,
.issue-line {
  color: var(--muted);
  font-size: 12px;
}

.issue-list {
  padding: 10px 12px;
}

.issue-line {
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
</style>

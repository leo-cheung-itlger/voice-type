<template>
  <div class="history-page">
    <div class="page-header">
      <h2>识别历史</h2>
      <div class="header-actions">
        <button @click="store.fetchHistory()" class="btn btn-ghost">刷新</button>
        <button @click="store.clearHistory()" class="btn btn-danger btn-small">清空</button>
      </div>
    </div>

    <div class="history-list">
      <div v-for="(entry, i) in reversedHistory" :key="entry.task_id + i" class="card history-entry" :class="{ marked: entry.marked }">
        <div class="entry-header">
          <span class="entry-time">{{ formatTime(entry.timestamp) }}</span>
          <span class="entry-delay">{{ entry.delay.toFixed(2) }}s</span>
        </div>
        <div class="entry-text">{{ entry.text }}</div>
        <div class="entry-actions">
          <button @click="store.copyToClipboard(entry.text)" class="btn btn-ghost btn-small">复制</button>
          <button @click="toggleMark(entry)" class="btn btn-ghost btn-small" :class="{ 'btn-mark-active': entry.marked }">
            {{ entry.marked ? '取消标记' : '标记错误' }}
          </button>
        </div>
        <div v-if="entry.marked" class="mark-form">
          <input v-model="entry.marked_words_text" placeholder="输入错误字词，用逗号分隔" class="mark-input" />
          <button @click="submitMark(entry)" class="btn btn-success btn-small">保存</button>
        </div>
      </div>
      <div v-if="store.history.length === 0" class="empty">暂无识别记录</div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { computed, onMounted } from 'vue'
import { useAppStore, type HistoryEntry } from '../stores/app'

const store = useAppStore()
const reversedHistory = computed(() => [...store.history].reverse())

function formatTime(ts: number): string {
  return new Date(ts * 1000).toLocaleTimeString('zh-CN', { hour: '2-digit', minute: '2-digit', second: '2-digit' })
}

function toggleMark(entry: HistoryEntry) {
  entry.marked = !entry.marked
  if (entry.marked && !entry.marked_words_text) {
    entry.marked_words_text = ''
  }
}

async function submitMark(entry: HistoryEntry) {
  if (entry.marked_words_text) {
    await store.addErrorMark(entry.text, entry.marked_words_text!)
  }
}

onMounted(() => store.fetchHistory())
</script>

<style scoped>
.history-page { padding: 24px; max-width: 900px; margin: 0 auto; }
.page-header { display: flex; justify-content: space-between; align-items: center; margin-bottom: 20px; }
.page-header h2 { font-size: 20px; }
.header-actions { display: flex; gap: 8px; }
.history-entry { margin-bottom: 8px; }
.history-entry.marked { border-color: var(--accent-yellow); }
.entry-header { display: flex; justify-content: space-between; margin-bottom: 6px; }
.entry-time { color: var(--text-secondary); font-size: 12px; }
.entry-delay { color: var(--accent-blue); font-size: 12px; }
.entry-text { font-size: 15px; line-height: 1.6; margin-bottom: 8px; }
.entry-actions { display: flex; gap: 8px; }
.btn-mark-active { border-color: var(--accent-yellow) !important; color: var(--accent-yellow) !important; }
.mark-form { display: flex; gap: 8px; margin-top: 8px; padding-top: 8px; border-top: 1px solid var(--bg-overlay); }
.mark-input { flex: 1; padding: 6px 12px; border-radius: 6px; border: 1px solid var(--bg-overlay); background: var(--bg-base); color: var(--text-primary); font-size: 13px; outline: none; }
.mark-input:focus { border-color: var(--accent-blue); }
.empty { color: var(--text-muted); text-align: center; padding: 40px; }
</style>

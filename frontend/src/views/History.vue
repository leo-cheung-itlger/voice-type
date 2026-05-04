<template>
  <div class="view">
    <section class="section">
      <div class="section-title">
        <span>识别历史</span>
        <div class="actions">
          <button class="btn btn-small btn-ghost" @click="store.openHistoryAudioRoot()">音频目录</button>
          <button class="btn btn-small btn-ghost" @click="store.openHistoryResultRoot()">结果目录</button>
          <button class="btn btn-small btn-ghost" @click="store.fetchHistory()">刷新</button>
          <button class="btn btn-small btn-ghost" @click="store.clearHistory()">清空</button>
        </div>
      </div>
      <div class="history-list">
        <article v-for="entry in reversedHistory" :key="entry.task_id" class="history-item" @click="store.copyToClipboard(entry.text)">
          <div class="item-meta">
            <span>{{ formatTime(entry.timestamp) }}</span>
            <span>{{ formatDuration(entry) }}</span>
          </div>
          <p>{{ entry.text }}</p>
          <div class="item-actions">
            <button class="btn btn-small btn-ghost" @click.stop="store.copyToClipboard(entry.text)">复制</button>
            <button class="btn btn-small btn-ghost" @click.stop="markEntry(entry)">标记</button>
            <button v-if="entry.audio_path" class="btn btn-small btn-ghost" @click.stop="store.openHistoryAudioFolder(entry.task_id)">音频目录</button>
            <button v-if="entry.transcript_path" class="btn btn-small btn-ghost" @click.stop="store.openHistoryResultFolder(entry.task_id)">结果目录</button>
            <button class="btn btn-small btn-ghost" @click.stop="store.deleteHistoryEntry(entry.task_id)">删除</button>
          </div>
          <div v-if="entry.marked" class="mark-row" @click.stop>
            <input v-model="entry.marked_words_text" class="field" placeholder="错误字词或修正建议" />
            <button class="btn btn-small btn-primary" @click="submitMark(entry)">保存</button>
          </div>
        </article>
        <div v-if="store.history.length === 0" class="empty">暂无识别记录</div>
      </div>
    </section>
  </div>
</template>

<script setup lang="ts">
import { computed, onMounted } from 'vue'
import { useAppStore, type HistoryEntry } from '../stores/app'

const store = useAppStore()
const reversedHistory = computed(() => [...store.history].reverse())

function formatTime(ts: number): string {
  return new Date(ts * 1000).toLocaleString('zh-CN', {
    month: '2-digit',
    day: '2-digit',
    hour: '2-digit',
    minute: '2-digit',
  })
}

function formatDuration(entry: HistoryEntry): string {
  return `推理 ${Number(entry.duration_seconds ?? entry.delay ?? 0).toFixed(1)}s`
}

function markEntry(entry: HistoryEntry) {
  entry.marked = !entry.marked
  entry.marked_words_text ||= ''
}

async function submitMark(entry: HistoryEntry) {
  if (entry.marked_words_text?.trim()) {
    await store.addErrorMark(entry.text, entry.marked_words_text.trim())
    entry.marked = false
  }
}

onMounted(() => store.fetchHistory())
</script>

<style scoped>
.actions,
.item-actions,
.mark-row {
  display: flex;
  gap: 7px;
}

.actions,
.item-actions {
  flex-wrap: wrap;
  justify-content: flex-end;
}

.history-list {
  display: grid;
  gap: 9px;
}

.history-item {
  min-width: 0;
  padding: 12px;
  border: 1px solid var(--line);
  border-radius: 12px;
  background: var(--panel);
  cursor: pointer;
}

.item-meta {
  display: flex;
  justify-content: space-between;
  gap: 10px;
  margin-bottom: 7px;
  color: var(--muted);
  font-size: 12px;
}

.history-item p {
  min-width: 0;
  font-size: 15px;
  line-height: 1.55;
  overflow-wrap: anywhere;
  white-space: normal;
  word-break: break-word;
}

.item-actions {
  margin-top: 10px;
}

.mark-row {
  margin-top: 9px;
}

.mark-row .field {
  min-width: 0;
}
</style>

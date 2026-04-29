<template>
  <div class="view">
    <section class="section stat-grid">
      <div>
        <strong>{{ store.totalEntries }}</strong>
        <span>总次数</span>
      </div>
      <div>
        <strong>{{ store.avgDelay }}s</strong>
        <span>平均延迟</span>
      </div>
      <div>
        <strong>{{ store.errorMarks.length }}</strong>
        <span>错误标记</span>
      </div>
    </section>

    <section class="section">
      <div class="section-title">
        <span>常用片段</span>
        <button class="btn btn-small btn-ghost" @click="refresh">刷新</button>
      </div>
      <div class="panel word-list">
        <div v-for="item in store.topWords.slice(0, 18)" :key="item.word" class="word-row">
          <span>{{ item.word }}</span>
          <div><i :style="{ width: barWidth(item.count) + '%' }"></i></div>
          <em>{{ item.count }}</em>
        </div>
        <div v-if="store.topWords.length === 0" class="empty">暂无统计</div>
      </div>
    </section>

    <section class="section">
      <div class="section-title"><span>错误标记</span></div>
      <div class="panel error-list">
        <div v-for="(mark, i) in store.errorMarks" :key="i" class="error-row">
          <p>{{ mark.text }}</p>
          <span>{{ mark.marked_text }}</span>
        </div>
        <div v-if="store.errorMarks.length === 0" class="empty">暂无错误标记</div>
      </div>
    </section>
  </div>
</template>

<script setup lang="ts">
import { onMounted } from 'vue'
import { useAppStore } from '../stores/app'

const store = useAppStore()

function barWidth(count: number): number {
  const max = store.topWords[0]?.count || 1
  return Math.max(8, (count / max) * 100)
}

function refresh() {
  store.fetchStats()
  store.fetchErrorMarks()
}

onMounted(refresh)
</script>

<style scoped>
.stat-grid {
  display: grid;
  grid-template-columns: repeat(3, 1fr);
  gap: 8px;
}

.stat-grid div {
  padding: 12px;
  border: 1px solid var(--line);
  border-radius: 12px;
  background: var(--panel);
}

.stat-grid strong,
.stat-grid span {
  display: block;
}

.stat-grid strong {
  font-size: 20px;
}

.stat-grid span {
  margin-top: 3px;
  color: var(--muted);
  font-size: 12px;
}

.word-list,
.error-list {
  overflow: hidden;
}

.word-row {
  display: grid;
  grid-template-columns: 86px 1fr 36px;
  align-items: center;
  gap: 8px;
  padding: 8px 11px;
  border-bottom: 1px solid var(--line);
}

.word-row:last-child,
.error-row:last-child {
  border-bottom: 0;
}

.word-row span {
  overflow: hidden;
  font-size: 13px;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.word-row div {
  height: 8px;
  overflow: hidden;
  border-radius: 999px;
  background: #101211;
}

.word-row i {
  display: block;
  height: 100%;
  border-radius: inherit;
  background: var(--accent-2);
}

.word-row em {
  color: var(--muted);
  font-size: 12px;
  font-style: normal;
  text-align: right;
}

.error-row {
  padding: 10px 12px;
  border-bottom: 1px solid var(--line);
}

.error-row p {
  margin-bottom: 4px;
  font-size: 13px;
}

.error-row span {
  color: var(--accent);
  font-size: 12px;
}
</style>

<template>
  <div class="stats-page">
    <h2>使用统计</h2>

    <div class="stats-summary">
      <div class="card stat-card">
        <span class="stat-number">{{ store.totalEntries }}</span>
        <span class="stat-desc">总识别次数</span>
      </div>
      <div class="card stat-card">
        <span class="stat-number">{{ store.avgDelay }}s</span>
        <span class="stat-desc">平均延迟</span>
      </div>
      <div class="card stat-card">
        <span class="stat-number">{{ store.errorMarks.length }}</span>
        <span class="stat-desc">错误标记</span>
      </div>
    </div>

    <div class="card section">
      <h3>常用词组 TOP 20</h3>
      <div class="word-chart">
        <div v-for="item in store.topWords.slice(0, 20)" :key="item.word" class="word-bar">
          <span class="word-label">{{ item.word }}</span>
          <div class="bar-track"><div class="bar-fill" :style="{ width: barWidth(item.count) + '%' }"></div></div>
          <span class="word-count">{{ item.count }}</span>
        </div>
        <div v-if="store.topWords.length === 0" class="empty">暂无数据</div>
      </div>
    </div>

    <div class="card section">
      <h3>错误标记列表</h3>
      <div class="error-list">
        <div v-for="(mark, i) in store.errorMarks" :key="i" class="error-item">
          <span class="error-original">{{ mark.text }}</span>
          <span class="error-arrow">→</span>
          <span class="error-marked">{{ mark.marked_text }}</span>
        </div>
        <div v-if="store.errorMarks.length === 0" class="empty">暂无错误标记</div>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { onMounted } from 'vue'
import { useAppStore } from '../stores/app'

const store = useAppStore()

function barWidth(count: number): number {
  const max = store.topWords[0]?.count || 1
  return (count / max) * 100
}

onMounted(() => {
  store.fetchStats()
  store.fetchErrorMarks()
})
</script>

<style scoped>
.stats-page { padding: 24px; max-width: 900px; margin: 0 auto; }
.stats-page h2 { margin-bottom: 16px; }
.stats-summary { display: flex; gap: 16px; margin-bottom: 20px; }
.stat-card { flex: 1; text-align: center; }
.stat-number { display: block; font-size: 28px; font-weight: 700; color: var(--accent-blue); }
.stat-desc { display: block; font-size: 12px; color: var(--text-secondary); margin-top: 4px; }
.section { margin-bottom: 20px; }
.section h3 { margin-bottom: 12px; font-size: 15px; }
.word-chart { display: flex; flex-direction: column; gap: 4px; }
.word-bar { display: flex; align-items: center; gap: 8px; }
.word-label { width: 80px; text-align: right; font-size: 13px; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.bar-track { flex: 1; height: 16px; background: var(--bg-base); border-radius: 4px; overflow: hidden; }
.bar-fill { height: 100%; background: linear-gradient(90deg, var(--accent-blue), var(--accent-teal)); border-radius: 4px; transition: width 0.3s; }
.word-count { width: 40px; color: var(--text-secondary); font-size: 12px; }
.error-list { display: flex; flex-direction: column; gap: 4px; }
.error-item { display: flex; align-items: center; gap: 8px; padding: 8px 12px; border-radius: 8px; background: var(--bg-base); }
.error-original { color: var(--accent-red); font-size: 13px; }
.error-arrow { color: var(--text-muted); }
.error-marked { color: var(--accent-green); font-size: 13px; }
.empty { color: var(--text-muted); text-align: center; padding: 20px; }
</style>

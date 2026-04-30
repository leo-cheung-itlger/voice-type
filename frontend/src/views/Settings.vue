<template>
  <div class="view">
    <section class="section">
      <div class="section-title">
        <span>运行设置</span>
        <button class="btn btn-small btn-primary" @click="save">保存</button>
      </div>
      <div class="panel">
        <label class="row setting-row">
          <span>
            <span class="value">输出模式</span>
            <span class="label">客户端重启后完全生效</span>
          </span>
          <select v-model="store.config.client.output_mode" class="field compact">
            <option value="clipboard">剪贴板</option>
            <option value="keyboard">键盘模拟</option>
            <option value="hybrid">混合</option>
          </select>
        </label>
        <label class="row setting-row">
          <span>
            <span class="value">快捷键</span>
            <span class="label">当前测试推荐 right shift</span>
          </span>
          <input v-model="store.config.client.shortcut_key" class="field compact" />
        </label>
        <label class="row setting-row">
          <span>
            <span class="value">保存录音</span>
            <span class="label">写入 data/recordings</span>
          </span>
          <input v-model="store.config.client.save_audio" type="checkbox" />
        </label>
        <label class="row setting-row">
          <span>
            <span class="value">录音提醒</span>
            <span class="label">右上角置顶小提示</span>
          </span>
          <input v-model="store.config.client.notification_enabled" type="checkbox" />
        </label>
        <label class="row setting-row">
          <span>
            <span class="value">提示音</span>
            <span class="label">开始和结束各响一声</span>
          </span>
          <input v-model="store.config.client.notification_sound" type="checkbox" />
        </label>
        <label class="row setting-row">
          <span>
            <span class="value">GPU</span>
            <span class="label">服务端重启后生效</span>
          </span>
          <input v-model="store.config.server.gpu" type="checkbox" />
        </label>
      </div>
    </section>

    <section class="section">
      <div class="section-title">
        <span>硬件</span>
        <button class="btn btn-small btn-ghost" @click="store.fetchHardware()">刷新</button>
      </div>
      <div class="panel">
        <div class="row">
          <div>
            <div class="value">{{ store.hardware?.nvidia_gpu ? 'NVIDIA GPU 已检测' : '未检测到 NVIDIA GPU' }}</div>
            <div class="label">{{ gpuLabel }}</div>
          </div>
          <span class="model-state" :class="{ ok: store.hardware?.torch.cuda_available }">
            {{ store.hardware?.torch.cuda_available ? 'CUDA OK' : 'CPU' }}
          </span>
        </div>
        <div class="row">
          <div>
            <div class="value">PyTorch</div>
            <div class="label">{{ torchLabel }}</div>
          </div>
          <span class="label">{{ store.hardware?.memory_gb ? `${store.hardware.memory_gb}GB RAM` : '-' }}</span>
        </div>
      </div>
    </section>

    <section class="section">
      <div class="section-title">
        <span>模型</span>
        <button class="btn btn-small btn-ghost" @click="refreshModels">刷新</button>
      </div>
      <div class="model-list">
        <button
          v-for="model in store.models"
          :key="model.id"
          class="model-row"
          :class="{ active: store.config.server.model === model.id }"
          @click="store.selectModel(model.id)"
        >
          <span>
            <strong>{{ model.name }}</strong>
            <small>{{ modelSummary(model) }}</small>
          </span>
          <span class="model-state" :class="{ ok: model.exists }">{{ model.exists ? 'OK' : 'MISS' }}</span>
        </button>
      </div>
      <div class="benchmark-actions">
        <button
          class="btn btn-small btn-primary"
          :disabled="benchmarking"
          @click="benchmarkSelected"
        >
          {{ benchmarking ? '测试中' : '测试当前模型' }}
        </button>
        <span class="label">{{ benchmarkHint }}</span>
      </div>
    </section>

    <section class="section">
      <div class="section-title">
        <span>最近日志</span>
        <button class="btn btn-small btn-ghost" @click="store.fetchLogs()">刷新</button>
      </div>
      <div class="panel logs">
        <div v-for="(item, i) in store.logs.slice(-24)" :key="i" class="log-line">
          <span>{{ item.file }}</span>
          <p>{{ item.line }}</p>
        </div>
        <div v-if="store.logs.length === 0" class="empty">暂无日志</div>
      </div>
    </section>
  </div>
</template>

<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import { type ModelEntry, useAppStore } from '../stores/app'

const store = useAppStore()
const benchmarking = ref(false)

const gpuLabel = computed(() => {
  const gpus = store.hardware?.gpus || []
  if (!gpus.length) return store.hardware?.recommendation || '等待检测'
  return gpus.map((gpu) => gpu.memory_total_mb ? `${gpu.name} ${Math.round(gpu.memory_total_mb / 1024)}GB` : gpu.name).join(' / ')
})

const torchLabel = computed(() => {
  const torch = store.hardware?.torch
  if (!torch) return '等待检测'
  if (!torch.available) return torch.error || '不可用'
  return `${torch.version}${torch.cuda_available ? ` · CUDA ${torch.cuda_version || ''}` : ' · CUDA 不可用'}`
})

const benchmarkHint = computed(() => {
  const model = store.config.server.model
  const result = store.benchmarks[model]
  if (!result) return '用于判断 0.6B/1.7B 在本机的真实耗时'
  if (!result.exists) return '模型未安装'
  if (!result.ok) return result.error || '测试失败'
  return `最近耗时 ${Number(result.recognition_seconds || 0).toFixed(2)}s`
})

async function save() {
  await store.saveConfig()
  await Promise.all([store.fetchStatus(), store.fetchModels()])
}

function modelSummary(model: ModelEntry) {
  const parts = [model.exists ? '已安装' : '未安装', model.backend || 'unknown']
  if (model.role === 'daily') parts.push('日用候选')
  if (model.role === 'quality') parts.push('高质量')
  const bench = model.benchmark || store.benchmarks[model.id]
  if (bench?.ok) parts.push(`${Number(bench.recognition_seconds || 0).toFixed(2)}s`)
  if (bench && !bench.ok && bench.error) parts.push('测试失败')
  return parts.join(' · ')
}

async function refreshModels() {
  await Promise.all([store.fetchModels(), store.fetchBenchmarks(), store.fetchHardware()])
}

async function benchmarkSelected() {
  benchmarking.value = true
  try {
    await store.runBenchmark(store.config.server.model)
  } finally {
    benchmarking.value = false
  }
}

onMounted(() => {
  store.fetchConfig()
  store.fetchModels()
  store.fetchHardware()
  store.fetchBenchmarks()
  store.fetchLogs()
})
</script>

<style scoped>
.setting-row > span:first-child {
  display: grid;
  gap: 3px;
}

.compact {
  width: 150px;
}

input[type="checkbox"] {
  width: 18px;
  height: 18px;
  accent-color: var(--accent);
}

.model-list {
  display: grid;
  gap: 8px;
}

.model-row {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
  width: 100%;
  padding: 12px;
  border: 1px solid var(--line);
  border-radius: 12px;
  color: var(--text);
  background: var(--panel);
  cursor: pointer;
  text-align: left;
}

.model-row.active {
  border-color: rgba(125, 220, 155, 0.55);
}

.model-row strong,
.model-row small {
  display: block;
}

.model-row small {
  margin-top: 3px;
  color: var(--muted);
}

.model-state {
  color: var(--danger);
  font-size: 11px;
}

.model-state.ok {
  color: var(--accent);
}

.benchmark-actions {
  display: flex;
  align-items: center;
  gap: 10px;
  margin-top: 10px;
}

.logs {
  max-height: 260px;
  overflow: auto;
  padding: 8px;
}

.log-line {
  display: grid;
  gap: 3px;
  padding: 7px;
  border-bottom: 1px solid var(--line);
}

.log-line:last-child {
  border-bottom: 0;
}

.log-line span {
  color: var(--faint);
  font-size: 11px;
}

.log-line p {
  color: var(--muted);
  font-size: 12px;
  line-height: 1.35;
  word-break: break-word;
}
</style>

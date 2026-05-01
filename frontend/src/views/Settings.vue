<template>
  <div class="view">
    <section class="section">
      <div class="section-title">
        <span>运行设置</span>
        <div class="actions">
          <span class="label">{{ saveState }}</span>
          <button class="btn btn-small btn-primary" @click="save">保存</button>
        </div>
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
            <span class="label">{{ captureMode ? '请按下要绑定的实体键' : '客户端重启后生效' }}</span>
          </span>
          <div class="inline-controls">
            <button class="btn btn-small" :class="captureMode ? 'btn-primary' : 'btn-ghost'" @click="toggleCapture">
              {{ captureMode ? '监听中' : store.config.client.shortcut_key }}
            </button>
            <input v-model="store.config.client.shortcut_key" class="field compact key-field" />
          </div>
        </label>
        <label class="row setting-row">
          <span>
            <span class="value">短按忽略</span>
            <span class="label">低于该时长不保存、不识别</span>
          </span>
          <input v-model.number="store.config.client.min_press_seconds" type="number" min="0" max="2" step="0.05" class="field compact" />
        </label>
        <label class="row setting-row">
          <span>
            <span class="value">保存录音</span>
            <span class="label">写入结构化归档目录</span>
          </span>
          <input v-model="store.config.client.save_audio" type="checkbox" />
        </label>
        <label class="row setting-row">
          <span>
            <span class="value">归档目录</span>
            <span class="label">按日期和任务保存 recording.wav/result.json</span>
          </span>
          <input v-model="store.config.client.archive_root" class="field path-field" />
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
            <span class="value">GPU 加速</span>
            <span class="label">{{ store.accelerationState.detail }}</span>
          </span>
          <input v-model="store.config.server.gpu" type="checkbox" />
        </label>
        <label class="row setting-row">
          <span>
            <span class="value">加速后端</span>
            <span class="label">CUDA / Vulkan / DirectML，服务端重启后生效</span>
          </span>
          <select v-model="store.config.server.gpu_backend" class="field compact">
            <option value="cuda">CUDA</option>
            <option value="vulkan">Vulkan</option>
            <option value="dml">DirectML</option>
          </select>
        </label>
        <div class="restart-row">
          <span class="label">快捷键、输出模式、录音参数等修改后，重启客户端才会完全生效。</span>
          <button class="btn btn-small btn-ghost" @click="restartClient">重启客户端</button>
        </div>
      </div>
    </section>

    <section class="section">
      <div class="section-title">
        <span>硬件与加速</span>
        <button class="btn btn-small btn-ghost" @click="store.fetchHardware()">刷新</button>
      </div>
      <div class="panel">
        <div class="row">
          <div>
            <div class="value">{{ store.hardware?.nvidia_gpu ? 'NVIDIA GPU 已检测' : '未检测到 NVIDIA GPU' }}</div>
            <div class="label">{{ gpuLabel }}</div>
          </div>
          <span class="model-state" :class="{ ok: store.accelerationState.active }">
            {{ store.accelerationState.label }}
          </span>
        </div>
        <div class="row">
          <div>
            <div class="value">PyTorch</div>
            <div class="label">{{ torchLabel }}</div>
          </div>
          <span class="label">{{ store.hardware?.memory_gb ? `${store.hardware.memory_gb}GB RAM` : '-' }}</span>
        </div>
        <div class="state-grid">
          <div>
            <span>GPU</span>
            <strong :class="{ ok: store.hardware?.nvidia_gpu }">{{ store.hardware?.nvidia_gpu ? '已检测' : '缺失' }}</strong>
          </div>
          <div>
            <span>CUDA</span>
            <strong :class="{ ok: store.accelerationState.cudaReady }">{{ store.accelerationState.cudaReady ? '可用' : '受阻' }}</strong>
          </div>
          <div>
            <span>Vulkan</span>
            <strong :class="{ ok: store.accelerationState.vulkanSelected && store.accelerationState.blocks.length === 0 }">
              {{ store.accelerationState.vulkanSelected ? '已选择' : '未选择' }}
            </strong>
          </div>
        </div>
        <div v-if="store.accelerationState.blocks.length" class="block-list">
          <div v-for="block in store.accelerationState.blocks" :key="block">{{ block }}</div>
        </div>
        <div class="recommendation-panel">
          <div>
            <div class="value">推荐：{{ store.accelerationRecommendation.modelName }}</div>
            <div class="label">{{ store.accelerationRecommendation.reason }}</div>
          </div>
          <button class="btn btn-small btn-primary" @click="applyRecommendation">应用推荐</button>
        </div>
      </div>
    </section>

    <section class="section">
      <div class="section-title">
        <span>模型</span>
        <button class="btn btn-small btn-ghost" @click="refreshModels">刷新</button>
      </div>
      <div class="model-list">
        <div
          v-for="model in store.models"
          :key="model.id"
          class="model-row"
          :class="{ active: store.config.server.model === model.id }"
        >
          <span>
            <strong>{{ model.name }}</strong>
            <small>{{ modelSummary(model) }}</small>
          </span>
          <div class="model-actions">
            <a v-if="!model.exists && model.download_url" class="btn btn-small btn-ghost" :href="model.download_url" target="_blank" rel="noreferrer">下载</a>
            <button class="btn btn-small btn-ghost" @click="store.openModelFolder(model.id)">打开</button>
            <button class="btn btn-small" :class="store.config.server.model === model.id ? 'btn-primary' : 'btn-ghost'" @click="store.selectModel(model.id)">
              {{ store.config.server.model === model.id ? '已选' : '选择' }}
            </button>
            <span class="model-state" :class="{ ok: model.exists }">{{ model.exists ? 'OK' : 'MISS' }}</span>
          </div>
        </div>
      </div>
      <div class="benchmark-actions">
        <button
          class="btn btn-small btn-primary"
          :disabled="benchmarking"
          @click="benchmarkSelected"
        >
          {{ benchmarking ? '测试中' : '测试当前模型' }}
        </button>
        <button
          class="btn btn-small btn-ghost"
          :disabled="benchmarking"
          @click="benchmarkAll"
        >
          {{ benchmarking ? '队列中' : '测试全部已安装' }}
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
import { computed, onBeforeUnmount, onMounted, ref, watch } from 'vue'
import { type ModelEntry, useAppStore } from '../stores/app'

const store = useAppStore()
const benchmarking = ref(false)
const captureMode = ref(false)
const saveState = ref('自动保存')
let saveTimer: ReturnType<typeof setTimeout> | null = null
let saveStarted = false

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
  const model = store.models.find((item) => item.id === store.config.server.model)
  const result = model ? bestBenchmark(model) : store.benchmarks[store.config.server.model]
  if (!result) return '用于判断 0.6B/1.7B 在本机的真实耗时'
  if (!result.exists) return '模型未安装'
  if (!result.ok) return result.error || '测试失败'
  return `最近耗时 ${Number(result.recognition_seconds || result.inference_seconds || 0).toFixed(2)}s · ${result.acceleration || 'unknown'}`
})

async function save() {
  saveState.value = '保存中'
  await store.saveConfig()
  await Promise.all([store.fetchStatus(), store.fetchModels()])
  saveState.value = store.lastError ? '保存失败' : '已保存'
}

function queueSave() {
  if (!saveStarted) return
  saveState.value = '等待保存'
  if (saveTimer) clearTimeout(saveTimer)
  saveTimer = setTimeout(() => {
    save().catch(() => {
      saveState.value = '保存失败'
    })
  }, 700)
}

function toggleCapture() {
  captureMode.value = !captureMode.value
}

function normalizeKey(event: KeyboardEvent) {
  if (event.code === 'ShiftRight') return 'right shift'
  if (event.code === 'ShiftLeft') return 'left shift'
  if (event.code === 'ControlRight') return 'right ctrl'
  if (event.code === 'ControlLeft') return 'left ctrl'
  if (event.code === 'AltRight') return 'right alt'
  if (event.code === 'AltLeft') return 'left alt'
  if (event.code === 'CapsLock') return 'caps lock'
  if (/^F\d{1,2}$/.test(event.code)) return event.code.toLowerCase()
  if (/^Key[A-Z]$/.test(event.code)) return event.code.slice(3).toLowerCase()
  if (/^Digit\d$/.test(event.code)) return event.code.slice(5)
  return event.key.toLowerCase().replace(/\s+/g, ' ')
}

function onCaptureKeydown(event: KeyboardEvent) {
  if (!captureMode.value) return
  event.preventDefault()
  event.stopPropagation()
  store.config.client.shortcut_key = normalizeKey(event)
  captureMode.value = false
}

async function restartClient() {
  await save()
  await store.restartClient()
}

function modelSummary(model: ModelEntry) {
  const parts = [model.exists ? '已安装' : '未安装', model.backend || 'unknown']
  if (model.role === 'daily') parts.push('日用候选')
  if (model.role === 'quality') parts.push('高质量')
  if (model.blocking_reason) parts.push(blockingLabel(model.blocking_reason))
  const bench = bestBenchmark(model)
  if (bench?.ok) {
    const mode = bench.actual_gpu ? 'GPU' : 'CPU'
    parts.push(`${mode} ${Number(bench.recognition_seconds || bench.inference_seconds || 0).toFixed(2)}s`)
  }
  if (bench && !bench.ok && bench.error) parts.push(`${bench.acceleration || '测试'}失败`)
  return parts.join(' · ')
}

function bestBenchmark(model: ModelEntry) {
  const gpuOnly = Boolean(store.config.server.gpu_required && !store.config.server.allow_cpu_fallback)
  const candidates = [
    model.benchmark,
    store.benchmarks[model.id],
    ...Object.values(model.benchmarks || {}),
  ].filter(Boolean)
  const successful = candidates
    .filter((bench) => bench?.ok && Number(bench.recognition_seconds || bench.inference_seconds || 0) > 0)
    .filter((bench) => !gpuOnly || bench?.actual_gpu)
    .sort((a, b) => Number(a?.recognition_seconds || a?.inference_seconds || 0) - Number(b?.recognition_seconds || b?.inference_seconds || 0))
  if (successful.length) return successful[0]
  return candidates
    .filter((bench) => !gpuOnly || bench?.actual_gpu || /cuda|vulkan|dml/.test(bench?.acceleration || ''))
    .sort((a, b) => Number(b?.updated_at || 0) - Number(a?.updated_at || 0))[0] || null
}

function blockingLabel(reason: string) {
  const labels: Record<string, string> = {
    model_missing: '模型缺失',
    cuda_unavailable: 'CUDA 受阻',
    gguf_vulkan_missing: 'Vulkan 缺失',
    cpu_only_model_blocked_by_gpu_required: 'CPU-only 已阻止',
  }
  return labels[reason] || reason
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

async function benchmarkAll() {
  benchmarking.value = true
  try {
    await store.runAllBenchmarks()
  } finally {
    benchmarking.value = false
  }
}

async function applyRecommendation() {
  await store.applyAccelerationRecommendation()
}

onMounted(() => {
  store.fetchConfig()
  store.fetchModels()
  store.fetchHardware()
  store.fetchBenchmarks()
  store.fetchLogs()
  window.addEventListener('keydown', onCaptureKeydown, true)
  window.setTimeout(() => {
    saveStarted = true
  }, 800)
})

onBeforeUnmount(() => {
  window.removeEventListener('keydown', onCaptureKeydown, true)
  if (saveTimer) clearTimeout(saveTimer)
})

watch(
  () => JSON.stringify(store.config),
  () => queueSave(),
)
</script>

<style scoped>
.setting-row > span:first-child {
  display: grid;
  gap: 3px;
}

.actions,
.inline-controls,
.model-actions,
.restart-row {
  display: flex;
  align-items: center;
  gap: 8px;
}

.compact {
  width: 150px;
}

.key-field {
  width: 112px;
}

.path-field {
  width: min(230px, 48vw);
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

.restart-row {
  justify-content: space-between;
  padding-top: 10px;
  border-top: 1px solid var(--line);
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

.model-actions {
  flex: 0 0 auto;
}

.model-actions .btn {
  min-width: 0;
}

.model-state {
  color: var(--danger);
  font-size: 11px;
}

.model-state.ok {
  color: var(--accent);
}

.state-grid {
  display: grid;
  grid-template-columns: repeat(3, 1fr);
  gap: 8px;
  margin-top: 10px;
}

.state-grid div {
  min-width: 0;
  padding: 9px;
  border: 1px solid var(--line);
  border-radius: 10px;
  background: var(--panel-2);
}

.state-grid span,
.state-grid strong {
  display: block;
}

.state-grid span {
  color: var(--muted);
  font-size: 11px;
}

.state-grid strong {
  margin-top: 3px;
  overflow: hidden;
  color: var(--danger);
  font-size: 12px;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.state-grid strong.ok {
  color: var(--accent);
}

.block-list {
  display: grid;
  gap: 6px;
  margin-top: 10px;
}

.block-list div {
  padding: 8px 10px;
  border: 1px solid rgba(255, 199, 120, 0.26);
  border-radius: 10px;
  color: var(--warn);
  background: rgba(255, 199, 120, 0.08);
  font-size: 12px;
  line-height: 1.35;
}

.recommendation-panel {
  display: grid;
  grid-template-columns: 1fr auto;
  gap: 10px;
  align-items: center;
  margin-top: 10px;
  padding-top: 10px;
  border-top: 1px solid var(--line);
}

.benchmark-actions {
  display: flex;
  align-items: center;
  flex-wrap: wrap;
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

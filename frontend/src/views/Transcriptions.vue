<template>
  <div class="view">
    <section class="section">
      <div class="section-title">
        <span>音视频转字幕</span>
        <button class="btn btn-small btn-ghost" @click="refresh">刷新</button>
      </div>
      <div
        class="drop-zone"
        :class="{ active: dragging }"
        @dragover.prevent="dragging = true"
        @dragleave.prevent="dragging = false"
        @drop.prevent="onDrop"
      >
        <input ref="fileInput" type="file" multiple class="hidden-input" :accept="accepts" @change="onPick" />
        <button class="btn btn-primary" @click="fileInput?.click()">选择文件</button>
        <p>拖入 mp3、mp4、wav、mkv、mov 等文件后创建后台队列</p>
        <small v-if="store.ffmpeg && !store.ffmpeg.available">{{ store.ffmpeg.message }}</small>
        <small v-else>浏览器选择的文件会先上传到本地缓存；绝对路径模式可输出到源文件旁边。</small>
      </div>
    </section>

    <section class="section">
      <div class="section-title"><span>任务设置</span></div>
      <div class="panel">
        <label class="row setting-row">
          <span>
            <span class="value">模型</span>
            <span class="label">文件转录独立于右 Shift 输入</span>
          </span>
          <select v-model="selectedModel" class="field compact">
            <option value="">使用当前模型</option>
            <option v-for="model in store.models" :key="model.id" :value="model.id" :disabled="!model.exists">
              {{ model.name }}{{ model.exists ? '' : ' - 缺失' }}
            </option>
          </select>
        </label>
        <div class="row setting-row align-start">
          <span>
            <span class="value">导出格式</span>
            <span class="label">JSON 为源结果，TXT/SRT 从 JSON 生成</span>
          </span>
          <div class="checks">
            <label><input v-model="formats" type="checkbox" value="json" /> JSON</label>
            <label><input v-model="formats" type="checkbox" value="txt" /> TXT</label>
            <label><input v-model="formats" type="checkbox" value="srt" /> SRT</label>
          </div>
        </div>
        <label class="row setting-row">
          <span>
            <span class="value">AI 润色</span>
            <span class="label">只用于文件转录，不接实时输入</span>
          </span>
          <input v-model="polish" type="checkbox" :disabled="!llmReady" />
        </label>
        <label class="row setting-row">
          <span>
            <span class="value">润色模式</span>
            <span class="label">{{ llmReady ? 'OpenAI 兼容接口已配置' : '请先填写 API key 和模型' }}</span>
          </span>
          <select v-model="polishMode" class="field compact" :disabled="!polish">
            <option value="correct">仅纠错</option>
            <option value="deoralize">去口语化</option>
            <option value="formal">书面化</option>
          </select>
        </label>
      </div>
    </section>

    <section class="section">
      <div class="section-title"><span>绝对路径任务</span></div>
      <div class="panel path-panel">
        <textarea v-model="pathText" class="field path-field" placeholder="每行一个本机绝对路径，例如 C:\Videos\demo.mp4"></textarea>
        <input v-model="outputDir" class="field" placeholder="可选：统一输出目录；留空则输出到源文件旁同名文件夹" />
        <button class="btn btn-primary" :disabled="!canCreatePathTask" @click="createPathTask">创建路径任务</button>
      </div>
    </section>

    <section v-if="pendingFiles.length" class="modal-mask">
      <div class="modal">
        <div class="section-title">
          <span>确认转录</span>
          <button class="btn btn-small btn-ghost" @click="pendingFiles = []">取消</button>
        </div>
        <div class="file-list">
          <div v-for="file in pendingFiles" :key="file.name" class="file-row">
            <span>{{ file.name }}</span>
            <small>{{ formatBytes(file.size) }}</small>
          </div>
        </div>
        <button class="btn btn-primary" :disabled="!store.ffmpeg?.available" @click="uploadPending">上传并创建任务</button>
      </div>
    </section>

    <section class="section">
      <div class="section-title"><span>队列</span></div>
      <div class="task-list">
        <div v-for="task in store.transcriptions" :key="task.task_id" class="task-row">
          <div class="task-head">
            <strong>{{ statusLabel(task.status) }}</strong>
            <span>{{ task.progress || 0 }}%</span>
          </div>
          <div class="bar"><span :style="{ width: `${task.progress || 0}%` }"></span></div>
          <p>{{ task.input_files.map(shortName).join('、') }}</p>
          <small v-if="task.error">{{ task.error }}</small>
          <div v-for="file in task.files" :key="file.path" class="output-row">
            <span>{{ shortName(file.path) }}</span>
            <small>{{ file.status }} {{ file.error || '' }}</small>
          </div>
          <button v-if="['queued','transcribing','polishing'].includes(task.status)" class="btn btn-small btn-ghost" @click="store.cancelTranscription(task.task_id)">
            取消
          </button>
        </div>
        <div v-if="store.transcriptions.length === 0" class="empty">暂无转录任务</div>
      </div>
    </section>

    <section class="section">
      <div class="section-title">
        <span>AI 配置</span>
        <button class="btn btn-small btn-primary" @click="store.saveLlmConfig()">保存</button>
      </div>
      <div class="panel path-panel">
        <input v-model="store.llmConfig.base_url" class="field" placeholder="OpenAI 兼容 base_url" />
        <input v-model="store.llmConfig.model" class="field" placeholder="模型名，例如 gpt-4.1-mini" />
        <input v-model="store.llmConfig.api_key" class="field" type="password" placeholder="API key，仅保存到本地 ignored 配置" />
        <div class="two-fields">
          <input v-model.number="store.llmConfig.temperature" class="field" type="number" min="0" max="2" step="0.1" placeholder="温度" />
          <input v-model.number="store.llmConfig.max_segment_chars" class="field" type="number" min="500" step="100" placeholder="每段最大字数" />
        </div>
      </div>
    </section>
  </div>
</template>

<script setup lang="ts">
import { computed, onMounted, onUnmounted, ref } from 'vue'
import { useAppStore } from '../stores/app'

const store = useAppStore()
const fileInput = ref<HTMLInputElement | null>(null)
const dragging = ref(false)
const pendingFiles = ref<File[]>([])
const selectedModel = ref('')
const formats = ref(['json', 'txt', 'srt'])
const polish = ref(false)
const polishMode = ref('correct')
const outputDir = ref('')
const pathText = ref('')
let timer: ReturnType<typeof setInterval> | null = null

const accepts = computed(() => store.ffmpeg?.supported_extensions?.join(',') || '.mp3,.wav,.mp4,.mkv,.mov')
const llmReady = computed(() => Boolean(store.llmConfig.model && store.llmConfig.api_key))
const canCreatePathTask = computed(() => Boolean(pathText.value.trim() && store.ffmpeg?.available && formats.value.length))

function payload() {
  return {
    model: selectedModel.value || undefined,
    output_dir: outputDir.value.trim() || undefined,
    formats: formats.value,
    polish: polish.value,
    polish_mode: polishMode.value,
  }
}

function onPick(event: Event) {
  const input = event.target as HTMLInputElement
  pendingFiles.value = Array.from(input.files || [])
  input.value = ''
}

function onDrop(event: DragEvent) {
  dragging.value = false
  pendingFiles.value = Array.from(event.dataTransfer?.files || [])
}

async function uploadPending() {
  await store.uploadTranscription(pendingFiles.value, payload())
  pendingFiles.value = []
}

async function createPathTask() {
  const input_files = pathText.value.split(/\r?\n/).map((line) => line.trim()).filter(Boolean)
  await store.createTranscription({ ...payload(), input_files })
  pathText.value = ''
}

function shortName(path: string) {
  return path.split(/[\\/]/).pop() || path
}

function statusLabel(status: string) {
  const labels: Record<string, string> = {
    queued: '等待中',
    transcribing: '转录中',
    polishing: '润色中',
    completed: '完成',
    failed: '失败',
    cancelled: '已取消',
  }
  return labels[status] || status
}

function formatBytes(size: number) {
  if (size < 1024 * 1024) return `${Math.round(size / 1024)} KB`
  return `${(size / 1024 / 1024).toFixed(1)} MB`
}

async function refresh() {
  await Promise.all([
    store.fetchFfmpegStatus(),
    store.fetchTranscriptions(),
    store.fetchModels(),
    store.fetchLlmConfig(),
  ])
}

onMounted(() => {
  refresh()
  timer = setInterval(() => store.fetchTranscriptions(), 2500)
})

onUnmounted(() => {
  if (timer) clearInterval(timer)
})
</script>

<style scoped>
.drop-zone {
  display: grid;
  gap: 9px;
  place-items: center;
  min-height: 150px;
  padding: 18px;
  border: 1px dashed rgba(125, 220, 155, 0.42);
  border-radius: 12px;
  background: rgba(125, 220, 155, 0.06);
  text-align: center;
  transition: border-color 0.16s ease, background 0.16s ease;
}

.drop-zone.active {
  border-color: var(--accent);
  background: rgba(125, 220, 155, 0.12);
}

.drop-zone p,
.drop-zone small {
  color: var(--muted);
  font-size: 12px;
  line-height: 1.45;
}

.hidden-input {
  display: none;
}

.setting-row > span:first-child {
  display: grid;
  gap: 3px;
}

.align-start {
  align-items: flex-start;
}

.compact {
  width: 170px;
}

.checks {
  display: grid;
  gap: 7px;
  color: var(--muted);
  font-size: 12px;
}

input[type="checkbox"] {
  width: 16px;
  height: 16px;
  accent-color: var(--accent);
}

.path-panel {
  display: grid;
  gap: 9px;
  padding: 10px;
}

.two-fields {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 8px;
}

.path-field {
  min-height: 92px;
}

.modal-mask {
  position: fixed;
  inset: 0;
  display: grid;
  place-items: center;
  padding: 18px;
  background: rgba(0, 0, 0, 0.55);
  z-index: 20;
}

.modal {
  width: min(440px, 100%);
  display: grid;
  gap: 12px;
  padding: 14px;
  border: 1px solid var(--line);
  border-radius: 12px;
  background: var(--panel);
  box-shadow: var(--shadow);
}

.file-list,
.task-list {
  display: grid;
  gap: 8px;
}

.file-row,
.output-row {
  display: flex;
  justify-content: space-between;
  gap: 10px;
  color: var(--muted);
  font-size: 12px;
}

.task-row {
  display: grid;
  gap: 8px;
  padding: 12px;
  border: 1px solid var(--line);
  border-radius: 12px;
  background: var(--panel);
}

.task-head {
  display: flex;
  justify-content: space-between;
  color: var(--text);
  font-size: 13px;
}

.task-row p,
.task-row small {
  color: var(--muted);
  font-size: 12px;
  line-height: 1.4;
  word-break: break-word;
}

.bar {
  height: 5px;
  overflow: hidden;
  border-radius: 999px;
  background: var(--panel-2);
}

.bar span {
  display: block;
  height: 100%;
  border-radius: inherit;
  background: var(--accent);
  transition: width 0.2s ease;
}
</style>

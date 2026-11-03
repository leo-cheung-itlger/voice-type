<template>
  <section v-if="store.apiReady && (needsCpu || showGpu || running || error)" class="panel setup-guide" aria-label="首次使用和 GPU 设置">
    <h2>{{ needsCpu ? '开始使用 VoiceType' : '可选 NVIDIA GPU 加速' }}</h2>
    <p v-if="needsCpu">先下载 SenseVoice CPU 模型（约 {{ size(cpu?.download_bytes || 163002883) }}），完成后自动启用普通话识别。其他语言和模型可在设置中选择。</p>
    <p v-else-if="showGpu">检测到 NVIDIA 显卡。可下载 GPU 运行组件与 Qwen 0.6B，验证驱动兼容性后自动启用；CPU 模型保留备用。</p>
    <p v-if="running" role="status">{{ stage }}<span v-if="progress"> · {{ progress }}</span></p>
    <p v-if="error" role="alert">{{ error }}</p>
    <div class="setup-actions">
      <button v-if="needsCpu" class="btn btn-primary" :disabled="running || store.busy" @click="setupCpu">下载并启用 CPU 模型</button>
      <button v-else-if="showGpu" class="btn" :disabled="running || preparing || store.busy" @click="prepareGpu">{{ preparing ? '读取下载大小…' : '查看 GPU 下载大小' }}</button>
      <button v-if="showGpu && !needsCpu && !running" class="btn btn-ghost" @click="dismissed = true">稍后设置</button>
    </div>
    <div v-if="approval" class="setup-confirm" role="dialog" aria-label="确认 GPU 下载">
      <p>GPU 组件：{{ size(approval.bytes) }}；Qwen 0.6B 模型：{{ gpu?.exists ? '已安装' : `约 ${size(gpu?.download_bytes || 1300000000)}` }}。</p>
      <p>GPU 运行组件解压后约 5 GB，安装期间还需临时下载空间。模型由官方模型源提供，许可见第三方说明。</p>
      <div class="setup-actions">
        <button class="btn btn-primary" :disabled="running" @click="setupGpu">确认下载并启用</button>
        <button class="btn btn-ghost" :disabled="running" @click="approval = null">取消</button>
      </div>
    </div>
  </section>
</template>

<script setup lang="ts">
import { computed, onMounted, onUnmounted, ref } from 'vue'
import { useAppStore } from '../stores/app'
import { useRoute } from 'vue-router'
const store = useAppStore()
const route = useRoute()
const cpu = computed(() => store.models.find(m => m.id === 'sensevoice'))
const gpu = computed(() => store.models.find(m => m.id === 'qwen3-asr-0.6b'))
const needsCpu = computed(() => store.models.length > 0 && !store.models.some(m => m.exists && m.implemented && m.compatible))
const dismissed = ref(false)
const showGpu = computed(() => (!dismissed.value || route.path === '/settings') && store.cudaComponent.portable && store.hardware?.nvidia_gpu && !store.config.server.model.startsWith('qwen3-asr'))
const running = ref(false)
const preparing = ref(false)
const stage = ref('')
const progress = ref('')
const error = ref('')
const approval = ref<{bytes: number; sha256: string} | null>(null)
let alive = true
const size = (bytes: number) => bytes >= 1e9 ? `${(bytes / 1e9).toFixed(2)} GB` : `${(bytes / 1e6).toFixed(1)} MB`
const pause = () => new Promise(resolve => setTimeout(resolve, 2000))
async function ensureModel(id: string) {
  await store.fetchModels()
  if (store.models.find(m => m.id === id)?.exists) return
  let job = await store.startModelScopeDownload(id)
  while (alive) {
    if (!job) throw new Error(store.lastError || '无法读取模型下载状态，请重试')
    if (job.status === 'error') throw new Error(job.error || job.message || '模型下载失败')
    if (job.status === 'done' || job.status === 'installed') break
    stage.value = job.message || '正在下载模型'
    progress.value = `${size(job.downloaded_bytes || 0)} / ${size(job.total_bytes || 0)}`
    await pause()
    if (!alive) return
    job = await store.fetchModelScopeDownload(id)
  }
  await store.fetchModels()
}
async function apply(id: string, mode: 'cpu' | 'auto') {
  if (!alive) return
  stage.value = '正在加载模型并启用识别'
  progress.value = ''
  const result = await store.applyRecognition(id, 'zh', mode)
  if (!result) throw new Error(store.lastError || '模型启用失败，请在设置中重试')
  stage.value = '设置完成，可在控制页开始语音输入'
  store.showToast(stage.value)
}
async function run(action: () => Promise<void>) {
  if (running.value) return
  running.value = true
  error.value = ''
  try { await action() } catch (e) { error.value = e instanceof Error ? e.message : String(e) }
  finally { running.value = false; progress.value = '' }
}
async function setupCpu() {
  await run(async () => { await ensureModel('sensevoice'); await apply('sensevoice', 'cpu') })
}
async function prepareGpu() {
  preparing.value = true
  error.value = ''
  try {
    await store.fetchCudaComponent()
    if (store.cudaComponent.installed) approval.value = {bytes: 0, sha256: ''}
    else {
      const plan = await store.fetchCudaPlan()
      if (!plan) throw new Error(store.lastError || '无法读取组件清单，请稍后重试')
      approval.value = plan
    }
  } catch (e) { error.value = String(e) }
  finally { preparing.value = false }
}
async function setupGpu() {
  const confirmed = approval.value
  if (!confirmed) return
  await run(async () => {
    // Keep a working CPU model/configuration before touching GPU setup.
    if (!cpu.value?.exists) { await ensureModel('sensevoice'); await apply('sensevoice', 'cpu') }
    if (!store.cudaComponent.installed) {
      let job = await store.installCudaComponent(confirmed.sha256)
      while (alive) {
        if (!job) throw new Error(store.lastError || '无法读取 GPU 安装状态')
        if (job.status === 'error') throw new Error(job.error || 'GPU 安装失败，可继续使用 CPU')
        if (job.status === 'done') break
        stage.value = job.message || '安装 GPU 组件'
        progress.value = `${size(job.downloaded_bytes || 0)} / ${size(job.total_bytes || confirmed.bytes)}`
        await pause()
        if (!alive) return
        job = await store.fetchCudaComponent()
      }
    }
    await store.fetchHardware()
    if (!store.hardware?.torch.cuda_available) throw new Error('当前 NVIDIA 驱动与 GPU 组件不兼容，请更新驱动后重试；CPU 可继续使用')
    await ensureModel('qwen3-asr-0.6b')
    await apply('qwen3-asr-0.6b', 'auto')
    approval.value = null
  })
}
onMounted(() => { store.fetchCudaComponent() })
onUnmounted(() => { alive = false })
</script>

<style scoped>
.setup-guide { margin-bottom: 16px; }
.setup-guide h2 { font-size: 16px; margin: 0 0 8px; }
.setup-guide p { font-size: 13px; line-height: 1.6; overflow-wrap: anywhere; }
.setup-actions { display: flex; gap: 8px; flex-wrap: wrap; }
.setup-confirm { border-top: 1px solid var(--border); margin-top: 12px; padding-top: 4px; }
</style>

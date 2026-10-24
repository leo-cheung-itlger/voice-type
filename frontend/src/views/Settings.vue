<template>
  <div class="view">
    <section id="models" class="section" tabindex="-1" aria-label="识别模型">
      <div class="section-title"><span>识别设置</span><button class="btn btn-small btn-ghost" @click="refreshModels">刷新</button></div>
      <p class="label model-help">{{ store.hardware?.recommendation || store.accelerationRecommendation.reason }} {{ store.hardware?.recommendation_reason || '' }} 模型会在你确认后下载。</p>
      <div class="panel">
        <label class="row setting-row"><span class="value">运行方式</span>
          <select v-model="draftMode" class="field compact" :disabled="settingsLocked"><option value="auto">自动选择</option><option value="cpu">CPU</option><option value="cuda">NVIDIA GPU</option></select>
        </label>
        <label class="row setting-row"><span class="value">识别语言</span>
          <select v-model="draftLanguage" class="field compact" :disabled="settingsLocked"><option v-for="(name, code) in languageNames" :key="code" :value="code" :disabled="!draftSpec?.languages.includes(code)">{{ name }}</option></select>
        </label>
        <div v-if="draftSpec && !draftSpec.language_hint" class="row label">此模型自动识别中文和英语，不支持强制指定语言；上述选择不会施加语言约束。</div>
        <div class="row"><span class="label">已配置：{{ store.selectedModel?.name }} · {{ languageNames[store.config.server.language] }}<br>正在使用：{{ store.runtime.loaded ? store.activeModelLabel : '未加载' }}</span></div>
      </div>
      <div v-if="store.hardware?.nvidia_gpu && !store.hardware?.torch.cuda_available && store.cudaComponent.portable" class="panel">
        <div class="row"><span><span class="value">可选 GPU 运行组件</span><span class="label">仅 NVIDIA 用户需要，下载体积见进度；CPU 模型无需安装。</span></span><button class="btn btn-small" :disabled="store.cudaComponent.status === 'running'" @click="store.installCudaComponent()">{{ store.cudaComponent.status === 'running' ? '下载中' : '下载组件' }}</button></div>
        <p class="label">{{ store.cudaComponent.error || store.cudaComponent.message }} <template v-if="store.cudaComponent.total_bytes">{{ formatSize(store.cudaComponent.downloaded_bytes || 0) }} / {{ formatSize(store.cudaComponent.total_bytes) }}</template></p>
      </div>
      <div class="model-list">
        <div v-for="model in store.models" :key="model.id" class="model-row" :class="{active: draftModel === model.id}">
          <span><strong>{{ model.name }}</strong><small>{{ modelSummary(model) }}</small><small v-if="model.implemented && !model.exists">下载约 {{ formatSize(model.download_bytes) }}</small></span>
          <div class="model-actions">
            <button v-if="model.implemented && !model.exists" class="btn btn-small btn-ghost" @click="downloadModel = model">下载</button>
            <button v-if="model.implemented" class="btn btn-small btn-ghost" @click="importingModel = model; importDirectory = ''">导入</button>
            <button class="btn btn-small" :class="draftModel === model.id ? 'btn-primary' : 'btn-ghost'" :disabled="!model.implemented || !model.exists || !modelCompatible(model) || settingsLocked" :aria-label="`选择 ${model.name}`" @click="chooseModel(model)">{{ draftModel === model.id ? '已选' : '选择' }}</button>
          </div>
        </div>
      </div>
      <div class="restart-row"><span class="label">{{ settingsLocked ? '正在录音、识别或转录，请完成后再修改' : '应用时会重新加载模型；失败时恢复原配置。' }}</span><button class="btn btn-primary" :disabled="settingsLocked || !draftSpec?.exists || !modelCompatible(draftSpec)" @click="applySettings">{{ store.applyingRecognition ? '正在应用…' : '应用并重启识别' }}</button></div>
      <p v-if="applyError" class="label danger" role="alert">{{ applyError }}</p>
    </section>

    <section class="section">
      <div class="section-title">
        <span>运行设置</span>
        <div class="actions">
          <span class="label">{{ saveState }}</span>
          <button class="btn btn-small btn-primary" @click="save(true)">保存</button>
        </div>
      </div>
      <div class="panel">
        <label class="row setting-row">
          <span>
            <span class="value">输出模式</span>
            <span class="label">保存后下次识别生效</span>
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
            <span class="label">{{ captureMode ? '请按下要绑定的实体键' : '保存后自动生效' }}</span>
          </span>
          <div class="inline-controls">
            <button class="btn btn-small" :class="captureMode ? 'btn-primary' : 'btn-ghost'" @click="toggleCapture">
              {{ captureMode ? '监听中' : displayShortcut(store.config.client.shortcut_key) }}
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
            <span class="value">麦克风</span>
            <span class="label" :class="{ danger: microphoneChanged }">{{ microphoneHint }}</span>
          </span>
          <div class="mic-stack">
            <div class="inline-controls mic-controls">
              <select v-model.number="selectedInputDevice" class="field mic-field" @change="onMicrophoneChange">
                <option :value="-1">智能默认麦克风</option>
                <option
                  v-for="device in visibleAudioDevices"
                  :key="device.index"
                  :value="device.index"
                >
                  {{ deviceLabel(device) }}
                </option>
              </select>
              <button class="btn btn-small btn-ghost" :disabled="store.audioInputTesting" @click.prevent="testMicrophone">
                {{ microphoneTestButtonLabel }}
              </button>
              <button class="btn btn-small btn-ghost" @click.prevent="openMicrophoneMonitor">高级检测</button>
              <button class="btn btn-small btn-ghost" @click.prevent="store.fetchAudioInputDevices()">刷新</button>
            </div>
            <div v-if="store.audioInputTesting" class="mic-progress">
              <div
                class="mic-progress-ring"
                :style="{ '--progress': `${Math.round(store.audioInputTestProgress * 360)}deg` }"
                aria-hidden="true"
              ></div>
              <span>{{ microphoneTestProgressLabel }}</span>
            </div>
            <div v-if="store.audioInputTest" class="mic-test" :class="{ ok: store.audioInputTest.has_signal }">
              {{ audioTestLabel }}
            </div>
          </div>
        </label>
        <label v-if="!store.audioInputDevices?.selected_exists" class="row setting-row warning-row">
          <span>
            <span class="value">麦克风不可用</span>
            <span class="label">当前选择的设备已消失，客户端会回退到真实麦克风优先的智能默认。</span>
          </span>
          <button class="btn btn-small btn-ghost" @click.prevent="resetMicrophone">使用默认</button>
        </label>
        <label class="row setting-row">
          <span>
            <span class="value">自动增益</span>
            <span class="label">低音量录音会自动放大并限制峰值</span>
          </span>
          <input v-model="store.config.client.auto_gain_enabled" type="checkbox" />
        </label>
        <label class="row setting-row">
          <span>
            <span class="value">Windows 语音增强采集</span>
            <span class="label">默认使用系统语音采集模式；失败时回退原录音方式</span>
          </span>
          <input v-model="store.config.client.windows_voice_capture_enabled" type="checkbox" />
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
        <div class="restart-row">
          <span class="label">快捷键、输出模式、麦克风会自动热加载；状态异常时可手动重启客户端。</span>
          <button class="btn btn-small btn-ghost" @click="restartClient">重启客户端</button>
        </div>
        <details class="build-details">
          <summary>版本与诊断信息</summary>
          <p>版本：{{ store.appVersionLabel }}</p>
          <p>构建标识：{{ store.appBuildLabel }}</p>
          <p>构建时间：{{ store.appBuildTime }}</p>
          <p>界面：{{ store.frontendSource === 'live-ui' ? '开发预览（源码更新后自动刷新）' : '正式构建' }}</p>
          <p>识别进程：{{ store.serverPid || '未运行' }} · 录音进程：{{ store.clientPid || '未运行' }}</p>
        </details>
      </div>
    </section>

    <details class="section build-details">
      <summary>高级：环境、日志与性能测试</summary>
      <p class="label">{{ gpuLabel }} · {{ torchLabel }}</p>
      <div class="benchmark-actions"><button class="btn btn-small btn-ghost" :disabled="benchmarking || store.serverRunning || store.busy" @click="benchmarkSelected">测试当前模型</button><span class="label">请先停止识别服务再运行独占测试。{{ benchmarkHint }}</span></div>
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
    </details>

    <div v-if="importingModel" class="modal-backdrop" @click.self="importingModel = null"><div class="modal" role="dialog" aria-modal="true" aria-label="导入本地模型"><label>导入 {{ importingModel.name }}<input v-model="importDirectory" class="field" placeholder="模型文件夹的完整路径" /></label><p class="label">只导入与此模型引擎匹配的文件；模型保留在原目录。</p><button class="btn btn-primary" :disabled="!importDirectory.trim()" @click="importLocal">验证并导入</button><button class="btn btn-ghost" @click="importingModel = null">取消</button></div></div>

    <div v-if="downloadModel" class="modal-backdrop" @click.self="downloadModel = null">
      <div class="modal" role="dialog" aria-modal="true" aria-label="下载模型">
        <div>
          <div class="value">下载 {{ downloadModel.name }}</div>
          <div class="label">{{ downloadHint(downloadModel) }}</div>
          <div class="label">国内镜像可用时优先使用，校验失败会回退官方源。</div>
        </div>
        <button
          v-if="downloadModel.modelscope_id"
          class="btn btn-primary"
          :disabled="downloadJob(downloadModel)?.status === 'running'"
          @click="startModelDownload(downloadModel)"
        >
          {{ downloadButtonLabel(downloadModel) }}
        </button>
        <div v-if="downloadJob(downloadModel)" class="download-status" :class="{ danger: downloadJob(downloadModel)?.status === 'error', ok: ['done', 'installed'].includes(downloadJob(downloadModel)?.status || '') }">
          {{ downloadStatusText(downloadModel) }}
        </div>
        <a
          v-if="downloadModel.download_url"
          class="btn btn-ghost"
          :href="downloadModel.download_url"
          target="_blank"
          rel="noreferrer"
        >
          打开官网网页
        </a>
        <button class="btn btn-ghost" @click="store.openModelFolder(downloadModel.id)">打开安装目录</button>
        <button class="btn btn-small btn-ghost" @click="downloadModel = null">关闭</button>
      </div>
    </div>

  </div>
</template>

<script setup lang="ts">
import { computed, onBeforeUnmount, onMounted, ref, watch } from 'vue'
import { useRouter } from 'vue-router'
import { type AudioInputDevice, type ModelEntry, useAppStore } from '../stores/app'

const store = useAppStore()
const languageNames: Record<string, string> = { zh: '普通话', auto: '自动检测', en: '英语', yue: '粤语', ja: '日语', ko: '韩语' }
const draftModel = ref(store.config.server.model)
const draftLanguage = ref(store.config.server.language)
const draftMode = ref(store.config.server.compute_mode)
const applyError = ref('')
const importingModel = ref<ModelEntry | null>(null)
const importDirectory = ref('')
const draftSpec = computed(() => store.models.find(m => m.id === draftModel.value))
const settingsLocked = computed(() => store.applyingRecognition || store.busy)
function modelCompatible(model: ModelEntry) {
  if (!model.implemented) return false
  if (draftMode.value === 'cuda') return model.backend === 'qwen-asr' && Boolean(store.hardware?.torch.cuda_available)
  return model.backend !== 'qwen-asr' || Boolean(store.hardware?.torch.available && store.hardware?.torch.qwen_available && (draftMode.value === 'cpu' || store.hardware?.torch.cuda_available))
}
function chooseModel(model: ModelEntry) {
  draftModel.value = model.id
  if (!model.languages.includes(draftLanguage.value)) draftLanguage.value = 'zh'
}
function formatSize(bytes: number) { return bytes >= 1e9 ? `${(bytes / 1e9).toFixed(1)} GB` : `${Math.round(bytes / 1e6)} MB` }
async function applySettings() {
  applyError.value = ''
  const data = await store.applyRecognition(draftModel.value, draftLanguage.value, draftMode.value)
  if (!data) applyError.value = store.lastError || store.toastMessage
}
async function importLocal() {
  if (importingModel.value && await store.importModel(importingModel.value.id, importDirectory.value.trim())) importingModel.value = null
}
const router = useRouter()
const benchmarking = ref(false)
const captureMode = ref(false)
const downloadModel = ref<ModelEntry | null>(null)
const saveState = ref('自动保存')
const activeClientShortcut = ref('')
const activeClientDevice = ref('')
const selectedInputDevice = ref(-1)
let saveTimer: ReturnType<typeof setTimeout> | null = null
let downloadPollTimer: ReturnType<typeof setInterval> | null = null
let saveStarted = false
let componentTimer: ReturnType<typeof setInterval> | null = null
let componentPolling = false

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
  const result = store.benchmarks[store.config.server.model]
  if (!result) return '用于判断 0.6B/1.7B 在本机的真实耗时'
  if (!result.exists) return '模型未安装'
  if (!result.ok) return result.error || '测试失败'
  return `最近耗时 ${Number(result.recognition_seconds || result.inference_seconds || 0).toFixed(2)}s · ${result.acceleration || 'unknown'}`
})

async function refreshModels() {
  await Promise.all([store.fetchModels(), store.fetchHardware()])
}

const microphoneHint = computed(() => {
  const devices = store.audioInputDevices
  if (!devices) return '等待检测输入设备'
  if (!devices.available) return devices.error || 'PyAudio 不可用'
  if (!devices.selected_exists) return '所选麦克风已不存在，将回退智能默认'
  if (microphoneChanged.value) return '保存后下次按键生效'
  const smartDefault = devices.smart_default_name ? `智能默认：${devices.smart_default_name}` : '保存后自动生效'
  return Number(store.config.client.input_device_index ?? -1) < 0 ? smartDefault : '保存后自动生效'
})

const visibleAudioDevices = computed(() => {
  const devices = store.audioInputDevices?.devices || []
  const candidates = devices.filter((device) => device.recommended || device.selected || device.is_default)
  const byName = new Map<string, AudioInputDevice>()
  for (const device of candidates) {
    const key = normalizedDeviceName(device.name)
    const existing = byName.get(key)
    if (!existing || deviceRank(device) < deviceRank(existing)) {
      byName.set(key, device)
    }
  }
  return [...byName.values()]
})

const audioTestLabel = computed(() => {
  const result = store.audioInputTest
  if (!result) return ''
  const rms = Number(result.rms_ratio || 0)
  const peak = Number(result.peak_ratio || 0)
  const device = result.device_name ? `${result.device_name} · ` : ''
  const profile = [
    result.capture_backend === 'windows_mediacapture' ? 'Windows 语音增强' : '',
    result.capture_host_api || result.host_api || '',
    result.sample_rate ? `${result.sample_rate}Hz` : '',
    result.capture_channels ? `${result.capture_channels}ch` : '',
    result.normalized_strategy || '',
  ].filter(Boolean).join(' · ')
  const gain = result.volume_policy === 'auto_gain_limited'
    ? ` · 增益 ${Number(result.gain_db || 0).toFixed(1)}dB`
    : ''
  const recognition = result.recognized_text ? ` · 识别：${result.recognized_text}` : result.recognition_error ? ` · 识别失败：${result.recognition_error}` : ''
  return `${device}${result.message}${profile ? ` · ${profile}` : ''}${gain} · RMS ${(rms * 100).toFixed(2)}% · Peak ${(peak * 100).toFixed(2)}%${recognition}`
})

const microphoneTestButtonLabel = computed(() => {
  if (store.audioInputTestPhase === 'recording') return '录音中'
  if (store.audioInputTestPhase === 'playing') return '播放中'
  return '测试'
})

const microphoneTestProgressLabel = computed(() => {
  const seconds = Math.max(0, Math.ceil((1 - Number(store.audioInputTestProgress || 0)) * 3))
  if (store.audioInputTestPhase === 'recording') return `录音 ${seconds}s`
  if (store.audioInputTestPhase === 'playing') return `播放 ${seconds}s`
  return '准备中'
})

const microphoneChanged = computed(() => deviceSignature() !== activeClientDevice.value)

async function save(promptRestart = false) {
  saveState.value = '保存中'
  await store.saveConfig()
  await Promise.all([store.fetchStatus(), store.fetchModels()])
  saveState.value = store.lastError ? '保存失败' : '已保存'
  if (!store.lastError) {
    activeClientShortcut.value = normalizeShortcut(store.config.client.shortcut_key)
    activeClientDevice.value = deviceSignature()
    if (promptRestart) store.showToast('已保存，下次按键自动生效')
  }
}

function queueSave() {
  if (!saveStarted) return
  saveState.value = '等待保存'
  if (saveTimer) clearTimeout(saveTimer)
  saveTimer = setTimeout(() => {
    save(false).catch(() => {
      saveState.value = '保存失败'
    })
  }, 700)
}

function toggleCapture() {
  captureMode.value = !captureMode.value
}

function normalizeKey(event: KeyboardEvent) {
  if (event.code === 'ShiftRight') return 'right_shift'
  if (event.code === 'ShiftLeft') return 'left_shift'
  if (event.code === 'ControlRight') return 'right_ctrl'
  if (event.code === 'ControlLeft') return 'left_ctrl'
  if (event.code === 'AltRight') return 'right_alt'
  if (event.code === 'AltLeft') return 'left_alt'
  if (event.code === 'CapsLock') return 'caps_lock'
  if (/^F\d{1,2}$/.test(event.code)) return event.code.toLowerCase()
  if (/^Key[A-Z]$/.test(event.code)) return event.code.slice(3).toLowerCase()
  if (/^Digit\d$/.test(event.code)) return event.code.slice(5)
  return normalizeShortcut(event.key)
}

function normalizeShortcut(value: string) {
  return (value || '').trim().toLowerCase().replace(/[-\s]+/g, '_')
}

function displayShortcut(value: string) {
  return normalizeShortcut(value)
    .split('_')
    .filter(Boolean)
    .map((part) => part.length === 1 ? part.toUpperCase() : part[0].toUpperCase() + part.slice(1))
    .join(' ')
}

function onCaptureKeydown(event: KeyboardEvent) {
  if (!captureMode.value) return
  event.preventDefault()
  event.stopPropagation()
  store.config.client.shortcut_key = normalizeKey(event)
  captureMode.value = false
}

function onMicrophoneChange() {
  const index = Number(selectedInputDevice.value)
  const device = store.audioInputDevices?.devices.find((item) => item.index === index)
  store.config.client.input_device_index = index
  store.config.client.input_device_name = device?.name || ''
  store.config.client.input_device_host_api = device?.host_api || ''
  store.config.client.input_device_sample_rate = Number(device?.default_sample_rate || 0)
}

function resetMicrophone() {
  selectedInputDevice.value = -1
  store.config.client.input_device_index = -1
  store.config.client.input_device_name = ''
  store.config.client.input_device_host_api = ''
  store.config.client.input_device_sample_rate = 0
}

function deviceLabel(device: AudioInputDevice) {
  return device.is_default ? `${device.name} · 默认` : device.name
}

function normalizedDeviceName(name: string) {
  return (name || '')
    .replace(/\s+/g, ' ')
    .replace(/\s*\([^)]*(capture|output)\)\s*/gi, '')
    .trim()
    .toLowerCase()
}

function deviceRank(device: AudioInputDevice) {
  const resolvedIndex = Number(store.audioInputDevices?.selected_resolved_index ?? -1)
  const resolvedBonus = device.index === resolvedIndex ? -500000 : 0
  const selectedBonus = device.selected ? -100000 : 0
  const defaultPenalty = device.is_default ? 20000 : 0
  const samplePenalty = Math.abs(Number(device.default_sample_rate || 48000) - 48000)
  const host = (device.host_api || '').toLowerCase()
  const hostPenalty = host.includes('wasapi') ? 0 : host.includes('directsound') ? 1000 : 10000
  return resolvedBonus + selectedBonus + defaultPenalty + hostPenalty + samplePenalty
}

function deviceSignature() {
  return [
    Number(store.config.client.input_device_index ?? -1),
    store.config.client.input_device_name || '',
    store.config.client.input_device_host_api || '',
    Number(store.config.client.input_device_sample_rate || 0),
    store.config.client.windows_voice_capture_enabled ? 'windows_voice' : 'pyaudio',
  ].join('|')
}

function selectedDeviceIndexForUi() {
  const resolved = Number(store.audioInputDevices?.selected_resolved_index ?? -1)
  if (resolved >= 0 && Number(store.config.client.input_device_index ?? -1) >= 0) return resolved
  return Number(store.config.client.input_device_index ?? -1)
}

async function testMicrophone() {
  const result = await store.testAudioInput(Number(selectedInputDevice.value ?? -1))
  if (result && !result.has_signal) {
    store.showToast('未检测到有效声音，建议切换同名 WASAPI/48000Hz 设备')
  } else if (result && !result.recognition_ok) {
    store.showToast(result.recognition_error || '录到了声音，但识别仍然失败')
  }
}

async function openMicrophoneMonitor() {
  const tauriWindow = window as any
  if (tauriWindow.__TAURI_INTERNALS__) {
    try {
      const mod = await import('@tauri-apps/api/core')
      await mod.invoke('open_microphone_monitor')
      return
    } catch (error) {
      store.showToast('改在当前窗口打开高级检测')
    }
  }
  await router.push('/microphones')
}

async function restartClient() {
  await save(false)
  await store.restartClient()
  activeClientShortcut.value = normalizeShortcut(store.config.client.shortcut_key)
  activeClientDevice.value = deviceSignature()
}

function modelSummary(model: ModelEntry) {
  if (!model.implemented) return '后端开发中，暂不可使用或下载'
  return [model.active ? '正在使用 · 加载成功' : model.exists ? '已安装 · 未加载' : '未安装', modelCompatible(model) ? '环境兼容' : '当前运行方式不兼容', model.id === store.accelerationRecommendation.model ? '推荐' : ''].filter(Boolean).join(' · ')
}
function downloadHint(model: ModelEntry) {
  return `${model.backend === 'sherpa-onnx' ? 'ONNX INT8 模型' : 'Qwen 模型权重'}，下载约 ${formatSize(model.download_bytes)}。失败后可重试。`
}

function downloadJob(model: ModelEntry) {
  return store.modelDownloads[model.id]
}

function downloadButtonLabel(model: ModelEntry) {
  const status = downloadJob(model)?.status
  if (status === 'running') return '正在下载'
  if (status === 'done' || status === 'installed') return '已下载'
  return status === 'error' ? '重试下载' : '下载模型'
}

function downloadStatusText(model: ModelEntry) {
  const job = downloadJob(model)
  if (!job) return ''
  if (job.status === 'error') return job.error || '下载失败'
  if (job.status === 'running') return `${job.message || '正在下载'} · ${formatSize(job.downloaded_bytes || 0)} / ${formatSize(job.total_bytes || model.download_bytes)}`
  if (job.status === 'done' || job.status === 'installed') return `${job.message || '下载完成'}${job.source ? ` · ${job.source}` : ''}`
  return job.message || ''
}

async function startModelDownload(model: ModelEntry) {
  const job = await store.startModelScopeDownload(model.id)
  if (!job) {
    store.showToast(store.lastError || '下载启动失败')
    return
  }
  store.showToast(job.message || '下载任务已启动')
  if (job.status === 'running') {
    startDownloadPolling(model.id)
  } else if (job.status === 'done' || job.status === 'installed') {
    await store.fetchModels()
  }
}

function startDownloadPolling(modelId: string) {
  if (downloadPollTimer) clearInterval(downloadPollTimer)
  downloadPollTimer = setInterval(async () => {
    const job = await store.fetchModelScopeDownload(modelId)
    if (!job || job.status === 'running') return
    if (downloadPollTimer) {
      clearInterval(downloadPollTimer)
      downloadPollTimer = null
    }
    await store.fetchModels()
    store.showToast(job.status === 'error' ? (job.error || '下载失败') : '模型下载完成')
  }, 3000)
}

async function benchmarkSelected() {
  benchmarking.value = true
  try {
    await store.runBenchmark(store.config.server.model)
  } finally {
    benchmarking.value = false
  }
}

onMounted(async () => {
  await store.fetchConfig()
  draftModel.value = store.config.server.model
  draftMode.value = store.config.server.compute_mode
  draftLanguage.value = store.config.server.language
  selectedInputDevice.value = selectedDeviceIndexForUi()
  activeClientShortcut.value = normalizeShortcut(store.config.client.shortcut_key)
  activeClientDevice.value = deviceSignature()
  store.fetchModels()
  store.fetchCudaComponent()
  componentTimer = setInterval(async () => {
    if (componentPolling || store.cudaComponent.status !== 'running') return
    componentPolling = true
    try { await store.fetchCudaComponent(); if (String(store.cudaComponent.status) === 'done') await store.fetchHardware() } finally { componentPolling = false }
  }, 3000)
  store.fetchHardware()
  store.fetchAudioInputDevices().then(() => {
    selectedInputDevice.value = selectedDeviceIndexForUi()
  })
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
  if (componentTimer) clearInterval(componentTimer)
  if (downloadPollTimer) clearInterval(downloadPollTimer)
})

watch(
  () => JSON.stringify(store.config),
  () => queueSave(),
)

watch(
  () => store.config.client.input_device_index,
  () => {
    selectedInputDevice.value = selectedDeviceIndexForUi()
  },
)

watch(
  () => store.audioInputDevices?.selected_resolved_index,
  () => {
    selectedInputDevice.value = selectedDeviceIndexForUi()
  },
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

.mic-controls {
  flex: 1;
  justify-content: flex-end;
}

.mic-stack {
  min-width: 0;
  display: grid;
  justify-items: end;
  gap: 6px;
}

.mic-field {
  width: min(100%, 300px);
}

.inline-check {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  color: var(--muted);
  font-size: 12px;
}

.inline-check input {
  width: 14px;
  height: 14px;
}

.mic-test {
  max-width: 360px;
  padding: 6px 8px;
  border: 1px solid rgba(242, 140, 140, 0.28);
  border-radius: 8px;
  color: var(--danger);
  background: rgba(242, 140, 140, 0.08);
  font-size: 12px;
  line-height: 1.35;
  text-align: right;
  overflow-wrap: anywhere;
}

.mic-progress {
  display: inline-flex;
  align-items: center;
  gap: 8px;
  color: var(--muted);
  font-size: 12px;
}

.mic-progress-ring {
  width: 24px;
  height: 24px;
  border-radius: 50%;
  background: conic-gradient(var(--accent) var(--progress), var(--panel-2) 0deg);
  position: relative;
}

.mic-progress-ring::after {
  content: "";
  position: absolute;
  inset: 4px;
  border-radius: inherit;
  background: var(--panel);
}

.mic-test.ok {
  border-color: rgba(125, 220, 155, 0.3);
  color: var(--accent);
  background: rgba(125, 220, 155, 0.08);
}

.warning-row {
  color: var(--warn);
  background: rgba(240, 195, 106, 0.06);
}

.compact-note {
  background: rgba(154, 216, 211, 0.04);
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

.danger {
  color: var(--danger);
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

.runtime-source-row {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 10px 13px;
  border-top: 1px solid var(--line);
}

.source-badge {
  padding: 4px 8px;
  border: 1px solid rgba(240, 195, 106, 0.32);
  border-radius: 999px;
  color: var(--warn);
  background: rgba(240, 195, 106, 0.08);
  font-size: 11px;
}

.source-badge.live {
  border-color: rgba(125, 220, 155, 0.4);
  color: var(--accent);
  background: rgba(125, 220, 155, 0.09);
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

.model-row > span {
  min-width: 0;
}

.model-row small {
  margin-top: 3px;
  color: var(--muted);
  overflow-wrap: anywhere;
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
  margin: 10px 13px 12px;
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

.modal-backdrop {
  position: fixed;
  inset: 0;
  z-index: 30;
  display: grid;
  place-items: center;
  padding: 18px;
  background: rgba(0, 0, 0, 0.45);
}

.modal {
  display: grid;
  gap: 10px;
  width: min(100%, 340px);
  padding: 16px;
  border: 1px solid var(--line);
  border-radius: 12px;
  background: var(--panel);
  box-shadow: var(--shadow);
}

.download-status {
  padding: 8px 10px;
  border: 1px solid var(--line);
  border-radius: 8px;
  color: var(--muted);
  font-size: 12px;
  line-height: 1.45;
  overflow-wrap: anywhere;
}

.download-status.ok {
  color: var(--ok);
}

.download-status.danger {
  color: var(--danger);
}

.modal-actions {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 8px;
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

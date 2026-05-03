<template>
  <div class="view mic-monitor">
    <section class="section monitor-header">
      <div>
        <div class="section-title">麦克风高级检测</div>
        <p class="label">
          逐个采样所有输入设备，显示当前 RMS/Peak 和简易波形。说话时，真正工作的麦克风应该明显跳动。
        </p>
      </div>
      <div class="monitor-actions">
        <button class="btn btn-small btn-primary" :disabled="store.audioLevelScanning" @click="scanOnce">
          {{ store.audioLevelScanning ? '扫描中' : '扫描一次' }}
        </button>
        <button class="btn btn-small" :class="monitoring ? 'btn-danger' : 'btn-ghost'" @click="toggleMonitor">
          {{ monitoring ? '停止监测' : '连续监测' }}
        </button>
      </div>
    </section>

    <section class="section">
      <div class="panel summary-panel">
        <div>
          <div class="value">检测到 {{ sortedDevices.length }} 个输入端</div>
          <div class="label">
            {{ store.audioLevelScan?.detected_count || 0 }} 个有明显输入 ·
            扫描耗时 {{ Number(store.audioLevelScan?.elapsed_seconds || 0).toFixed(1) }}s
          </div>
        </div>
        <div v-if="strongest" class="strongest">
          <span>最强输入</span>
          <strong>{{ displayName(strongest.name) }}</strong>
        </div>
      </div>
    </section>

    <section class="section">
      <div class="device-grid">
        <article
          v-for="device in sortedDevices"
          :key="device.index"
          class="device-card"
          :class="{ active: device.has_signal, selected: device.selected }"
        >
          <div class="device-top">
            <div>
              <div class="value">{{ displayName(device.name) }}</div>
              <div class="label">
                #{{ device.index }} · {{ device.host_api || 'Unknown' }} · {{ device.default_sample_rate }}Hz
              </div>
            </div>
            <span class="signal-badge" :class="{ on: device.has_signal }">
              {{ device.has_signal ? '有声音' : device.ok ? '安静' : '失败' }}
            </span>
          </div>

          <div class="meter">
            <span :style="{ width: `${levelPercent(device.rms_ratio)}%` }"></span>
          </div>

          <div class="waveform" aria-hidden="true">
            <span
              v-for="(point, index) in device.waveform"
              :key="index"
              :style="{ height: `${Math.max(2, point * 56)}px` }"
            ></span>
          </div>

          <div class="device-footer">
            <span>RMS {{ percent(device.rms_ratio) }} · Peak {{ percent(device.peak_ratio) }}</span>
            <button class="btn btn-small btn-ghost" @click="selectDevice(device)">使用</button>
          </div>
          <p v-if="!device.ok" class="device-error">{{ device.message }}</p>
        </article>
      </div>
      <div v-if="sortedDevices.length === 0" class="empty">暂无扫描结果</div>
    </section>
  </div>
</template>

<script setup lang="ts">
import { computed, onBeforeUnmount, onMounted, ref } from 'vue'
import { type AudioLevelDevice, useAppStore } from '../stores/app'

const store = useAppStore()
const monitoring = ref(false)
let timer: ReturnType<typeof setInterval> | null = null

const sortedDevices = computed(() => {
  const devices = store.audioLevelScan?.devices || []
  return [...devices].sort((a, b) => {
    if (a.has_signal !== b.has_signal) return a.has_signal ? -1 : 1
    return Number(b.rms_ratio || 0) - Number(a.rms_ratio || 0)
  })
})

const strongest = computed(() => store.audioLevelScan?.strongest || sortedDevices.value[0] || null)

function percent(value?: number) {
  return `${(Number(value || 0) * 100).toFixed(2)}%`
}

function levelPercent(value?: number) {
  return Math.min(100, Math.max(0, Number(value || 0) * 800))
}

function displayName(name: string) {
  return (name || '未知设备').replace(/\s*\([^)]*(capture|output)\)\s*/gi, '').trim()
}

async function scanOnce() {
  await store.scanAudioLevels(true)
}

function toggleMonitor() {
  monitoring.value = !monitoring.value
  if (monitoring.value) {
    scanOnce()
    timer = setInterval(() => {
      if (!store.audioLevelScanning) scanOnce()
    }, 2600)
  } else if (timer) {
    clearInterval(timer)
    timer = null
  }
}

async function selectDevice(device: AudioLevelDevice) {
  store.config.client.input_device_index = device.index
  store.config.client.input_device_name = device.name
  store.config.client.input_device_host_api = device.host_api || ''
  store.config.client.input_device_sample_rate = Number(device.default_sample_rate || 0)
  await store.saveConfig()
  store.showToast('已选择麦克风，下次按键自动生效')
}

onMounted(async () => {
  await Promise.all([store.fetchConfig(), store.fetchAudioInputDevices()])
  scanOnce()
})

onBeforeUnmount(() => {
  if (timer) clearInterval(timer)
})
</script>

<style scoped>
.monitor-header,
.summary-panel,
.device-top,
.device-footer {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
}

.monitor-actions {
  display: flex;
  flex: 0 0 auto;
  gap: 8px;
}

.summary-panel {
  padding: 13px;
}

.strongest {
  max-width: 220px;
  text-align: right;
}

.strongest span,
.strongest strong {
  display: block;
}

.strongest span {
  color: var(--muted);
  font-size: 11px;
}

.strongest strong {
  overflow: hidden;
  color: var(--accent);
  font-size: 13px;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.device-grid {
  display: grid;
  gap: 10px;
}

.device-card {
  min-width: 0;
  display: grid;
  gap: 10px;
  padding: 12px;
  border: 1px solid var(--line);
  border-radius: 12px;
  background: var(--panel);
}

.device-card.active {
  border-color: rgba(125, 220, 155, 0.42);
}

.device-card.selected {
  box-shadow: inset 3px 0 0 var(--accent);
}

.signal-badge {
  flex: 0 0 auto;
  padding: 4px 8px;
  border: 1px solid rgba(240, 195, 106, 0.25);
  border-radius: 999px;
  color: var(--warn);
  font-size: 11px;
}

.signal-badge.on {
  border-color: rgba(125, 220, 155, 0.4);
  color: var(--accent);
}

.meter {
  height: 7px;
  overflow: hidden;
  border-radius: 999px;
  background: var(--panel-2);
}

.meter span {
  display: block;
  height: 100%;
  border-radius: inherit;
  background: var(--accent);
}

.waveform {
  height: 60px;
  display: flex;
  align-items: center;
  gap: 2px;
  padding: 5px;
  border: 1px solid var(--line);
  border-radius: 10px;
  background: #101211;
}

.waveform span {
  flex: 1;
  min-width: 1px;
  border-radius: 999px;
  background: linear-gradient(180deg, var(--accent), var(--accent-2));
}

.device-footer {
  color: var(--muted);
  font-size: 12px;
}

.device-error {
  color: var(--danger);
  font-size: 12px;
  overflow-wrap: anywhere;
}
</style>

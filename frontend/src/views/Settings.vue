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
            <span class="label">默认 caps_lock</span>
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
      <div class="section-title"><span>模型</span></div>
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
            <small>{{ model.exists ? '已找到' : '缺失' }}</small>
          </span>
          <span class="model-state" :class="{ ok: model.exists }">{{ model.exists ? 'OK' : 'MISS' }}</span>
        </button>
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
import { onMounted } from 'vue'
import { useAppStore } from '../stores/app'

const store = useAppStore()

async function save() {
  await store.saveConfig()
  await Promise.all([store.fetchStatus(), store.fetchModels()])
}

onMounted(() => {
  store.fetchConfig()
  store.fetchModels()
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

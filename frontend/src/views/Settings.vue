<template>
  <div class="settings-page">
    <h2>设置</h2>

    <div class="card setting-group">
      <h3>输出模式</h3>
      <div class="setting-options">
        <label class="option" :class="{ active: store.outputMode === 'clipboard' }">
          <input type="radio" v-model="store.outputMode" value="clipboard" />
          <div class="option-content">
            <span class="option-title">剪贴板模式</span>
            <span class="option-desc">复制到剪贴板后模拟 Ctrl+V 粘贴（最稳定）</span>
          </div>
        </label>
        <label class="option" :class="{ active: store.outputMode === 'keyboard' }">
          <input type="radio" v-model="store.outputMode" value="keyboard" />
          <div class="option-content">
            <span class="option-title">键盘模拟打字</span>
            <span class="option-desc">逐字符模拟键盘输入，像打字一样</span>
          </div>
        </label>
        <label class="option" :class="{ active: store.outputMode === 'hybrid' }">
          <input type="radio" v-model="store.outputMode" value="hybrid" />
          <div class="option-content">
            <span class="option-title">混合模式</span>
            <span class="option-desc">英文/数字用键盘模拟，中文用剪贴板</span>
          </div>
        </label>
      </div>
    </div>

    <div class="card setting-group">
      <h3>关于</h3>
      <div class="about-info">
        <p>VoiceType v1.0.0</p>
        <p>独立重构的离线语音输入工具</p>
        <p>基于 sherpa-onnx + Qwen3-ASR / FunASR-Nano / SenseVoice</p>
        <p style="color: var(--accent-green);">本项目为独立开发，不包含任何第三方受限代码</p>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { useAppStore } from '../stores/app'
const store = useAppStore()
</script>

<style scoped>
.settings-page { padding: 24px; max-width: 900px; margin: 0 auto; }
.settings-page h2 { margin-bottom: 16px; }
.setting-group { margin-bottom: 16px; }
.setting-group h3 { margin-bottom: 12px; font-size: 15px; }
.setting-options { display: flex; flex-direction: column; gap: 8px; }
.option { display: flex; align-items: flex-start; gap: 12px; padding: 12px; border-radius: 8px; border: 1px solid var(--bg-overlay); cursor: pointer; transition: all 0.15s; }
.option:hover { background: rgba(137, 180, 250, 0.05); }
.option.active { border-color: var(--accent-blue); background: rgba(137, 180, 250, 0.1); }
.option input { margin-top: 4px; accent-color: var(--accent-blue); }
.option-content { display: flex; flex-direction: column; gap: 2px; }
.option-title { font-size: 14px; font-weight: 500; }
.option-desc { font-size: 12px; color: var(--text-secondary); }
.about-info { color: var(--text-secondary); font-size: 14px; line-height: 1.8; }
.about-info p { margin: 0; }
</style>

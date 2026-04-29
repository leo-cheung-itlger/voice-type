<template>
  <div class="view">
    <section class="section">
      <div class="section-title">
        <span>热词文件</span>
        <button class="btn btn-small btn-primary" @click="save">保存</button>
      </div>
      <div class="file-tabs">
        <button
          v-for="file in files"
          :key="file"
          class="file-tab"
          :class="{ active: store.selectedHotword === file }"
          @click="select(file)"
        >
          {{ file.replace('hot-', '').replace('.txt', '') }}
        </button>
      </div>
      <textarea v-model="content" class="field editor" spellcheck="false" />
    </section>

    <section class="section">
      <div class="section-title"><span>格式</span></div>
      <div class="panel help">
        <p>每行一条：识别结果 -&gt; 目标文本</p>
        <p>英文文件忽略大小写；规则文件左侧按正则表达式处理。</p>
        <p>保存后客户端会按自动 reload 周期生效。</p>
      </div>
    </section>
  </div>
</template>

<script setup lang="ts">
import { computed, onMounted } from 'vue'
import { useAppStore } from '../stores/app'

const store = useAppStore()
const files = ['hot-zh.txt', 'hot-en.txt', 'hot-rule.txt']
const content = computed({
  get: () => store.hotwordContent[store.selectedHotword] || '',
  set: (value: string) => {
    store.hotwordContent[store.selectedHotword] = value
  },
})

async function select(file: string) {
  await store.fetchHotword(file)
}

async function save() {
  await store.saveHotword()
}

onMounted(() => store.fetchHotword(store.selectedHotword))
</script>

<style scoped>
.file-tabs {
  display: grid;
  grid-template-columns: repeat(3, 1fr);
  gap: 7px;
  margin-bottom: 10px;
}

.file-tab {
  min-height: 34px;
  border-radius: 9px;
  color: var(--muted);
  background: var(--panel);
  cursor: pointer;
}

.file-tab.active {
  color: #08100b;
  background: var(--accent);
}

.editor {
  min-height: 300px;
  font-family: Consolas, "Cascadia Mono", monospace;
  font-size: 13px;
}

.help {
  padding: 12px;
}

.help p {
  margin-bottom: 7px;
  color: var(--muted);
  font-size: 12px;
  line-height: 1.5;
}

.help p:last-child {
  margin-bottom: 0;
}
</style>

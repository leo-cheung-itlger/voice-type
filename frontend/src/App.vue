<template>
  <div class="sidebar">
    <div class="sidebar-logo">VoiceType</div>
    <nav class="sidebar-nav">
      <router-link to="/" class="nav-item" :class="{ active: $route.path === '/' }">
        <span class="nav-icon">📊</span> 控制面板
      </router-link>
      <router-link to="/history" class="nav-item" :class="{ active: $route.path === '/history' }">
        <span class="nav-icon">📝</span> 识别历史
      </router-link>
      <router-link to="/stats" class="nav-item" :class="{ active: $route.path === '/stats' }">
        <span class="nav-icon">📈</span> 使用统计
      </router-link>
      <router-link to="/settings" class="nav-item" :class="{ active: $route.path === '/settings' }">
        <span class="nav-icon">⚙️</span> 设置
      </router-link>
    </nav>
  </div>
  <div class="main-content">
    <router-view />
  </div>
</template>

<script setup lang="ts">
</script>

import { createRouter, createWebHashHistory } from 'vue-router'

const router = createRouter({
  history: createWebHashHistory(),
  routes: [
    { path: '/', name: 'dashboard', component: () => import('../views/Dashboard.vue') },
    { path: '/transcriptions', name: 'transcriptions', component: () => import('../views/Transcriptions.vue') },
    { path: '/history', name: 'history', component: () => import('../views/History.vue') },
    { path: '/hotwords', name: 'hotwords', component: () => import('../views/Hotwords.vue') },
    { path: '/stats', name: 'stats', component: () => import('../views/Stats.vue') },
    { path: '/settings', name: 'settings', component: () => import('../views/Settings.vue') },
    { path: '/microphones', name: 'microphones', component: () => import('../views/MicrophoneMonitor.vue') },
  ],
})

export default router

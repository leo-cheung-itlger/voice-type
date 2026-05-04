import { defineConfig } from 'vite'
import vue from '@vitejs/plugin-vue'
import { execSync } from 'node:child_process'
import { readFileSync } from 'node:fs'
import { dirname, resolve } from 'node:path'
import { fileURLToPath } from 'node:url'

const rootDir = dirname(fileURLToPath(import.meta.url))
const packageJson = JSON.parse(readFileSync(resolve(rootDir, 'package.json'), 'utf-8')) as { version?: string }

function readGitValue(command: string, fallback: string) {
  try {
    return execSync(command, { cwd: rootDir, stdio: ['ignore', 'pipe', 'ignore'] }).toString().trim() || fallback
  } catch {
    return fallback
  }
}

const gitSha = readGitValue('git rev-parse --short=8 HEAD', 'nogit')
const gitDirty = readGitValue('git status --short', '') !== ''

export default defineConfig({
  plugins: [vue()],
  define: {
    __APP_VERSION__: JSON.stringify(packageJson.version || '0.0.0'),
    __APP_BUILD_SHA__: JSON.stringify(gitSha),
    __APP_BUILD_DIRTY__: JSON.stringify(gitDirty),
    __APP_BUILD_TIME__: JSON.stringify(new Date().toISOString()),
  },
  server: {
    port: 55343,
    strictPort: true,
    proxy: {
      '/api': {
        target: 'http://127.0.0.1:55342',
        changeOrigin: true,
      },
      '/ws': {
        target: 'ws://127.0.0.1:55342',
        ws: true,
      },
    },
  },
})

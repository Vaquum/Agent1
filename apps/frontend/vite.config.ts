import { defineConfig } from 'vitest/config'

const DEFAULT_API_PROXY_TARGET = 'http://localhost:8000'

function getApiProxyTarget(): string {
  const configuredApiProxyTarget = process.env.VITE_API_PROXY_TARGET ?? ''
  const normalizedApiProxyTarget = configuredApiProxyTarget.trim()
  if (normalizedApiProxyTarget === '') {
    return DEFAULT_API_PROXY_TARGET
  }

  return normalizedApiProxyTarget
}

export default defineConfig({
  server: {
    host: '0.0.0.0',
    port: 8080,
    strictPort: true,
    proxy: {
      '/api': {
        target: getApiProxyTarget(),
        changeOrigin: true,
        rewrite: (path) => path.replace(/^\/api/, '')
      }
    }
  },
  test: {
    include: ['src/**/*.test.ts'],
    environment: 'node'
  }
})

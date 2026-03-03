import { defineConfig, devices } from '@playwright/test'

const DASHBOARD_PORT = 4173

export default defineConfig({
  testDir: './tests/e2e',
  timeout: 30_000,
  expect: {
    timeout: 10_000
  },
  fullyParallel: false,
  retries: 1,
  use: {
    baseURL: `http://127.0.0.1:${DASHBOARD_PORT}`,
    trace: 'retain-on-failure'
  },
  projects: [
    {
      name: 'chromium',
      use: { ...devices['Desktop Chrome'] }
    }
  ],
  webServer: {
    command: `pnpm dev --host 127.0.0.1 --port ${DASHBOARD_PORT}`,
    port: DASHBOARD_PORT,
    reuseExistingServer: true
  }
})

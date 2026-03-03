import { test as base } from '@playwright/test'

export const test = base.extend<{ dashboardUrl: string }>({
  dashboardUrl: async ({ baseURL }, use) => {
    await use(baseURL ?? 'http://127.0.0.1:4173')
  }
})

export { expect } from '@playwright/test'

import { expect, test } from './fixtures'

test('renders dashboard shell for operator navigation', async ({ page, dashboardUrl }) => {
  await page.goto(dashboardUrl)

  await expect(page.getByRole('heading', { name: 'Agent1 Dashboard' })).toBeVisible()
  await expect(page.getByRole('heading', { name: 'Filters' })).toBeVisible()
  await expect(page.getByRole('heading', { name: 'Recent Jobs' })).toBeVisible()
})

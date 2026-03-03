import { expect, test } from './fixtures'

const OVERVIEW_PAYLOAD = {
  filters: {
    entity_key: null,
    job_id: null,
    trace_id: null,
    status: null
  },
  jobs_page: {
    limit: 20,
    offset: 0,
    total: 1
  },
  transitions_page: {
    limit: 20,
    offset: 0,
    total: 1
  },
  events_page: {
    limit: 20,
    offset: 0,
    total: 1
  },
  jobs: [
    {
      job_id: 'job_e2e_1',
      entity_key: 'Vaquum/Agent1#601',
      kind: 'issue',
      state: 'ready_to_execute',
      lease_epoch: 1,
      environment: 'dev',
      mode: 'active',
      updated_at: '2026-03-03T10:00:00Z'
    }
  ],
  transitions: [
    {
      job_id: 'job_e2e_1',
      from_state: 'awaiting_context',
      to_state: 'ready_to_execute',
      reason: 'context_refreshed',
      transition_at: '2026-03-03T10:00:01Z'
    }
  ],
  events: [
    {
      timestamp: '2026-03-03T10:00:02Z',
      trace_id: 'trc_e2e_1',
      job_id: 'job_e2e_1',
      entity_key: 'Vaquum/Agent1#601',
      source: 'agent',
      event_type: 'state_transition',
      status: 'ok',
      details: { reason: 'context_refreshed' }
    }
  ]
}

const TIMELINE_PAYLOAD = {
  job: {
    job_id: 'job_e2e_1',
    entity_key: 'Vaquum/Agent1#601',
    kind: 'issue',
    state: 'ready_to_execute',
    lease_epoch: 1,
    environment: 'dev',
    mode: 'active',
    updated_at: '2026-03-03T10:00:00Z'
  },
  transitions_page: {
    limit: 20,
    offset: 0,
    total: 1
  },
  events_page: {
    limit: 20,
    offset: 0,
    total: 1
  },
  transitions: [
    {
      job_id: 'job_e2e_1',
      from_state: 'awaiting_context',
      to_state: 'ready_to_execute',
      reason: 'context_refreshed',
      transition_at: '2026-03-03T10:00:01Z'
    }
  ],
  events: [
    {
      timestamp: '2026-03-03T10:00:02Z',
      trace_id: 'trc_e2e_1',
      job_id: 'job_e2e_1',
      entity_key: 'Vaquum/Agent1#601',
      source: 'agent',
      event_type: 'state_transition',
      status: 'ok',
      details: { reason: 'context_refreshed' }
    }
  ]
}

test('covers overview filter and timeline drill-down operator flow', async ({ page, dashboardUrl }) => {
  const overviewRequestUrls: string[] = []
  await page.route('**/dashboard/overview?*', async (route) => {
    overviewRequestUrls.push(route.request().url())
    await route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify(OVERVIEW_PAYLOAD)
    })
  })
  await page.route('**/dashboard/jobs/*/timeline?*', async (route) => {
    await route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify(TIMELINE_PAYLOAD)
    })
  })

  await page.goto(dashboardUrl)
  await expect(page.getByTestId('job-id-cell').first()).toHaveText('job_e2e_1')

  await page.locator('#filter-job-id').fill('job_e2e_1')
  const filterRequest = page.waitForRequest(
    (request) => request.url().includes('/dashboard/overview') && request.url().includes('job_id=job_e2e_1')
  )
  await page.getByRole('button', { name: 'Apply' }).click()
  await filterRequest

  await page.getByTestId('select-job-timeline').first().click()
  await expect(page.getByRole('heading', { name: 'Job Timeline: job_e2e_1' })).toBeVisible()

  await page.getByTestId('inspect-timeline-event').first().click()
  await expect(page.getByRole('heading', { name: 'Selected Timeline Event' })).toBeVisible()
  await expect(page.getByRole('heading', { name: 'Correlated Transitions' })).toBeVisible()

  expect(overviewRequestUrls.length).toBeGreaterThanOrEqual(2)
})

import { expect, test } from './fixtures'

const OVERVIEW_BASE_PAYLOAD = {
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
    total: 2
  },
  anomalies_page: {
    limit: 20,
    offset: 0,
    total: 0
  },
  jobs: [
    {
      job_id: 'job_e2e_trace_1',
      entity_key: 'Vaquum/Agent1#701',
      kind: 'issue',
      state: 'ready_to_execute',
      lease_epoch: 1,
      environment: 'dev',
      mode: 'active',
      updated_at: '2026-03-03T11:00:00Z'
    }
  ],
  transitions: [
    {
      job_id: 'job_e2e_trace_1',
      from_state: 'awaiting_context',
      to_state: 'ready_to_execute',
      reason: 'context_refreshed',
      transition_at: '2026-03-03T11:00:01Z'
    }
  ],
  events: [
    {
      timestamp: '2026-03-03T11:00:02Z',
      trace_id: 'trc_focus',
      job_id: 'job_e2e_trace_1',
      entity_key: 'Vaquum/Agent1#701',
      source: 'agent',
      event_type: 'state_transition',
      status: 'ok',
      details: { reason: 'context_refreshed', note: 'focus_trace' }
    },
    {
      timestamp: '2026-03-03T11:00:03Z',
      trace_id: 'trc_other',
      job_id: 'job_e2e_trace_1',
      entity_key: 'Vaquum/Agent1#701',
      source: 'agent',
      event_type: 'state_transition',
      status: 'ok',
      details: { reason: 'context_refreshed', note: 'other_trace' }
    }
  ],
  anomalies: []
}

const OVERVIEW_TRACE_FILTERED_PAYLOAD = {
  ...OVERVIEW_BASE_PAYLOAD,
  events_page: {
    limit: 20,
    offset: 0,
    total: 1
  },
  events: [OVERVIEW_BASE_PAYLOAD.events[0]]
}

const TIMELINE_PAYLOAD = {
  job: OVERVIEW_BASE_PAYLOAD.jobs[0],
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
  transitions: OVERVIEW_BASE_PAYLOAD.transitions,
  events: [OVERVIEW_BASE_PAYLOAD.events[0]]
}

test('covers event-detail inspection and trace-pivot filtering flow', async ({ page, dashboardUrl }) => {
  await page.route('**/dashboard/overview?*', async (route) => {
    const requestUrl = new URL(route.request().url())
    const traceFilter = requestUrl.searchParams.get('trace_id')
    const payload = traceFilter === 'trc_focus'
      ? OVERVIEW_TRACE_FILTERED_PAYLOAD
      : OVERVIEW_BASE_PAYLOAD
    await route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify(payload)
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
  await page.getByTestId('toggle-job-timeline').first().click()
  await expect(page.getByText('Timeline events (1)')).toBeVisible()

  await page.getByTestId('toggle-timeline-event').first().click()
  await expect(page.getByRole('heading', { name: 'Timeline Event Inspection' })).toBeVisible()
  await expect(page.getByText('"note": "focus_trace"')).toBeVisible()

  const tracePivotRequest = page.waitForRequest(
    (request) => request.url().includes('/dashboard/overview') && request.url().includes('trace_id=trc_focus')
  )
  await page.getByTestId('apply-trace-filter').click()
  await tracePivotRequest

  await expect(page.locator('#filter-trace-id')).toHaveValue('trc_focus')
  await page.locator("button.section-toggle[data-section='events']").click()
  await expect(page.getByTestId('overview-trace-cell').first()).toHaveText('trc_focus')
  await expect(page.getByTestId('overview-trace-cell').filter({ hasText: 'trc_other' })).toHaveCount(0)
})

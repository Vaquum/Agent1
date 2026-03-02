import { describe, expect, it } from 'vitest'

import { createDashboardMarkup } from './main'
import type { DashboardOverviewResponse } from './main'

describe('dashboard markup', () => {
  it('shows loading text when overview is absent', () => {
    const markup = createDashboardMarkup(null)

    expect(markup).toContain('Loading dashboard snapshot...')
  })

  it('renders jobs transitions and events from overview payload', () => {
    const payload: DashboardOverviewResponse = {
      jobs: [
        {
          job_id: 'job_1',
          entity_key: 'Vaquum/Agent1#1',
          kind: 'issue',
          state: 'ready_to_execute',
          lease_epoch: 1,
          environment: 'dev',
          mode: 'active',
          updated_at: '2026-03-02T20:00:00Z'
        }
      ],
      transitions: [
        {
          job_id: 'job_1',
          from_state: 'awaiting_context',
          to_state: 'ready_to_execute',
          reason: 'context_refresh',
          transition_at: '2026-03-02T20:01:00Z'
        }
      ],
      events: [
        {
          timestamp: '2026-03-02T20:02:00Z',
          trace_id: 'trc_1',
          job_id: 'job_1',
          entity_key: 'Vaquum/Agent1#1',
          source: 'agent',
          event_type: 'state_transition',
          status: 'ok',
          details: { reason: 'context_refresh' }
        }
      ]
    }

    const markup = createDashboardMarkup(payload)

    expect(markup).toContain('Agent1 Dashboard')
    expect(markup).toContain('job_1')
    expect(markup).toContain('trc_1')
    expect(markup).toContain('Live snapshot')
  })
})

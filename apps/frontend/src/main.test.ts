import { describe, expect, it } from 'vitest'

import { createDashboardMarkup } from './main'
import type { DashboardJobTimelineResponse } from './main'
import type { DashboardRenderState } from './main'
import type { DashboardOverviewResponse } from './main'

function createStateWithOverview(overview: DashboardOverviewResponse): DashboardRenderState {
  return {
    query: {
      limit: 20,
      offset: 0,
      entity_key: '',
      job_id: '',
      trace_id: '',
      status: ''
    },
    selected_job_id: null,
    timeline_offset: 0,
    selected_timeline_event_key: null,
    overview,
    timeline: null,
    is_loading: false,
    error_message: null
  }
}

describe('dashboard markup', () => {
  it('shows loading text when overview is absent', () => {
    const markup = createDashboardMarkup({
      query: {
        limit: 20,
        offset: 0,
        entity_key: '',
        job_id: '',
        trace_id: '',
        status: ''
      },
      selected_job_id: null,
      timeline_offset: 0,
      selected_timeline_event_key: null,
      overview: null,
      timeline: null,
      is_loading: true,
      error_message: null
    })

    expect(markup).toContain('Loading dashboard snapshot...')
  })

  it('renders jobs transitions and events from overview payload', () => {
    const payload: DashboardOverviewResponse = {
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

    const markup = createDashboardMarkup(createStateWithOverview(payload))

    expect(markup).toContain('Agent1 Dashboard')
    expect(markup).toContain('job_1')
    expect(markup).toContain('trc_1')
    expect(markup).toContain('Live snapshot')
    expect(markup).toContain('Filters')
    expect(markup).toContain('Timeline')
  })

  it('renders selected timeline event details and correlated transitions', () => {
    const overview: DashboardOverviewResponse = {
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
          job_id: 'job_2',
          entity_key: 'Vaquum/Agent1#2',
          kind: 'issue',
          state: 'executing',
          lease_epoch: 2,
          environment: 'dev',
          mode: 'active',
          updated_at: '2026-03-02T20:05:00Z'
        }
      ],
      transitions: [],
      events: []
    }
    const timeline: DashboardJobTimelineResponse = {
      job: {
        job_id: 'job_2',
        entity_key: 'Vaquum/Agent1#2',
        kind: 'issue',
        state: 'executing',
        lease_epoch: 2,
        environment: 'dev',
        mode: 'active',
        updated_at: '2026-03-02T20:05:00Z'
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
          job_id: 'job_2',
          from_state: 'ready_to_execute',
          to_state: 'executing',
          reason: 'context_refresh',
          transition_at: '2026-03-02T20:06:00Z'
        }
      ],
      events: [
        {
          timestamp: '2026-03-02T20:07:00Z',
          trace_id: 'trc_2',
          job_id: 'job_2',
          entity_key: 'Vaquum/Agent1#2',
          source: 'agent',
          event_type: 'state_transition',
          status: 'ok',
          details: { reason: 'context_refresh' }
        }
      ]
    }
    const state: DashboardRenderState = {
      query: {
        limit: 20,
        offset: 0,
        entity_key: '',
        job_id: '',
        trace_id: '',
        status: ''
      },
      selected_job_id: 'job_2',
      timeline_offset: 0,
      selected_timeline_event_key: '2026-03-02T20:07:00Z|trc_2|state_transition|ok',
      overview,
      timeline,
      is_loading: false,
      error_message: null
    }

    const markup = createDashboardMarkup(state)

    expect(markup).toContain('Selected Timeline Event')
    expect(markup).toContain('Correlated Transitions')
    expect(markup).toContain('context_refresh')
    expect(markup).toContain('Filter Overview by Trace')
  })
})

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
    active_view: 'snapshot',
    selected_job_id: null,
    timeline_offset: 0,
    selected_timeline_event_key: null,
    transitions_collapsed: true,
    events_collapsed: true,
    anomalies_collapsed: true,
    overview,
    timeline: null,
    active_repositories: [],
    controls_is_loading: false,
    controls_is_saving: false,
    controls_error_message: null,
    controls_feedback_message: null,
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
      active_view: 'snapshot',
      selected_job_id: null,
      timeline_offset: 0,
      selected_timeline_event_key: null,
      transitions_collapsed: true,
      events_collapsed: true,
      anomalies_collapsed: true,
      overview: null,
      timeline: null,
      active_repositories: [],
      controls_is_loading: false,
      controls_is_saving: false,
      controls_error_message: null,
      controls_feedback_message: null,
      is_loading: true,
      error_message: null
    })

    expect(markup).toContain('Snapshot syncing...')
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
      anomalies_page: {
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
      ],
      anomalies: [
        {
          timestamp: '2026-03-02T20:03:00Z',
          trace_id: 'trc_anomaly_1',
          job_id: 'system:event_chain',
          entity_key: 'system:event_chain',
          alert_name: 'hash_chain_gap_anomalies',
          severity: 'sev1',
          reason: 'event_journal_chain_validation_failed',
          runbook: 'docs/Developer/runbooks/event-journal-chain-validation.md',
          details: { finding_count: 1 }
        }
      ]
    }

    const markup = createDashboardMarkup(createStateWithOverview(payload))

    expect(markup).toContain('SNAPSHOT')
    expect(markup).toContain('CONTROLS')
    expect(markup).toContain('job_1')
    expect(markup).toContain('Snapshot ready')
    expect(markup).toContain('Filters')
    expect(markup).toContain('toggle-job-timeline')
    expect(markup).toContain('Recent Anomalies')
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
      anomalies_page: {
        limit: 20,
        offset: 0,
        total: 0
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
      events: [],
      anomalies: []
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
          details: {
            reason: 'context_refresh',
            transition_details: {
              error_type: 'RuntimeError',
              error_message: 'comment failure'
            }
          }
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
      active_view: 'snapshot',
      selected_job_id: 'job_2',
      timeline_offset: 0,
      selected_timeline_event_key: '2026-03-02T20:07:00Z|trc_2|state_transition|ok',
      transitions_collapsed: true,
      events_collapsed: true,
      anomalies_collapsed: true,
      overview,
      timeline,
      active_repositories: [],
      controls_is_loading: false,
      controls_is_saving: false,
      controls_error_message: null,
      controls_feedback_message: null,
      is_loading: false,
      error_message: null
    }

    const markup = createDashboardMarkup(state)

    expect(markup).toContain('Timeline Event Inspection')
    expect(markup).toContain('Correlated Transitions')
    expect(markup).toContain('context_refresh')
    expect(markup).toContain('Filter Overview by Trace')
    expect(markup).toContain('RuntimeError - comment failure')
  })

  it('shows timeline error summary without manual event selection', () => {
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
      anomalies_page: {
        limit: 20,
        offset: 0,
        total: 0
      },
      jobs: [
        {
          job_id: 'job_3',
          entity_key: 'Vaquum/Agent1#3',
          kind: 'issue',
          state: 'blocked',
          lease_epoch: 1,
          environment: 'prod',
          mode: 'active',
          updated_at: '2026-03-02T20:10:00Z'
        }
      ],
      transitions: [],
      events: [],
      anomalies: []
    }
    const timeline: DashboardJobTimelineResponse = {
      job: {
        job_id: 'job_3',
        entity_key: 'Vaquum/Agent1#3',
        kind: 'issue',
        state: 'blocked',
        lease_epoch: 1,
        environment: 'prod',
        mode: 'active',
        updated_at: '2026-03-02T20:10:00Z'
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
          job_id: 'job_3',
          from_state: 'ready_to_execute',
          to_state: 'blocked',
          reason: 'mention_response_failed',
          transition_at: '2026-03-02T20:11:00Z'
        }
      ],
      events: [
        {
          timestamp: '2026-03-02T20:11:01Z',
          trace_id: 'trc_3',
          job_id: 'job_3',
          entity_key: 'Vaquum/Agent1#3',
          source: 'agent',
          event_type: 'state_transition',
          status: 'ok',
          details: {
            reason: 'mention_response_failed',
            transition_details: {
              error_type: 'GitHubPolicyError',
              error_message: 'Mutating credential owner preflight mismatch'
            }
          }
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
      active_view: 'snapshot',
      selected_job_id: 'job_3',
      timeline_offset: 0,
      selected_timeline_event_key: '2026-03-02T20:11:01Z|trc_3|state_transition|ok',
      transitions_collapsed: true,
      events_collapsed: true,
      anomalies_collapsed: true,
      overview,
      timeline,
      active_repositories: [],
      controls_is_loading: false,
      controls_is_saving: false,
      controls_error_message: null,
      controls_feedback_message: null,
      is_loading: false,
      error_message: null
    }

    const markup = createDashboardMarkup(state)

    expect(markup).toContain('GitHubPolicyError - Mutating credential owner preflight mismatch')
  })

  it('shows blocked reason when timeline has no transition details', () => {
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
      anomalies_page: {
        limit: 20,
        offset: 0,
        total: 0
      },
      jobs: [
        {
          job_id: 'job_4',
          entity_key: 'Vaquum/Agent1#4',
          kind: 'issue',
          state: 'blocked',
          lease_epoch: 1,
          environment: 'prod',
          mode: 'active',
          updated_at: '2026-03-02T20:10:00Z'
        }
      ],
      transitions: [],
      events: [],
      anomalies: []
    }
    const timeline: DashboardJobTimelineResponse = {
      job: {
        job_id: 'job_4',
        entity_key: 'Vaquum/Agent1#4',
        kind: 'issue',
        state: 'blocked',
        lease_epoch: 1,
        environment: 'prod',
        mode: 'active',
        updated_at: '2026-03-02T20:10:00Z'
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
          job_id: 'job_4',
          from_state: 'ready_to_execute',
          to_state: 'blocked',
          reason: 'reviewer_response_failed',
          transition_at: '2026-03-02T20:11:00Z'
        }
      ],
      events: [
        {
          timestamp: '2026-03-02T20:11:01Z',
          trace_id: 'trc_4',
          job_id: 'job_4',
          entity_key: 'Vaquum/Agent1#4',
          source: 'agent',
          event_type: 'state_transition',
          status: 'ok',
          details: {
            action: 'transition_job',
            reason: 'reviewer_response_failed'
          }
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
      active_view: 'snapshot',
      selected_job_id: 'job_4',
      timeline_offset: 0,
      selected_timeline_event_key: null,
      transitions_collapsed: true,
      events_collapsed: true,
      anomalies_collapsed: true,
      overview,
      timeline,
      active_repositories: [],
      controls_is_loading: false,
      controls_is_saving: false,
      controls_error_message: null,
      controls_feedback_message: null,
      is_loading: false,
      error_message: null
    }

    const markup = createDashboardMarkup(state)

    expect(markup).toContain('reviewer_response_failed')
  })
})

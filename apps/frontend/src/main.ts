import './styles.css'

export interface DashboardJobSummary {
  job_id: string
  entity_key: string
  kind: string
  state: string
  lease_epoch: number
  environment: string
  mode: string
  updated_at: string
}

export interface DashboardTransitionSummary {
  job_id: string
  from_state: string
  to_state: string
  reason: string
  transition_at: string
}

export interface DashboardEventSummary {
  timestamp: string
  trace_id: string
  job_id: string
  entity_key: string
  source: string
  event_type: string
  status: string
  details: Record<string, unknown>
}

export interface DashboardAnomalySummary {
  timestamp: string
  trace_id: string
  job_id: string
  entity_key: string
  alert_name: string
  severity: string
  reason: string
  runbook: string
  details: Record<string, unknown>
}

export interface DashboardPageSummary {
  limit: number
  offset: number
  total: number
}

export interface DashboardOverviewFilters {
  entity_key: string | null
  job_id: string | null
  trace_id: string | null
  status: string | null
}

export interface DashboardOverviewResponse {
  filters: DashboardOverviewFilters
  jobs_page: DashboardPageSummary
  transitions_page: DashboardPageSummary
  events_page: DashboardPageSummary
  anomalies_page: DashboardPageSummary
  jobs: DashboardJobSummary[]
  transitions: DashboardTransitionSummary[]
  events: DashboardEventSummary[]
  anomalies: DashboardAnomalySummary[]
}

export interface DashboardJobTimelineResponse {
  job: DashboardJobSummary
  transitions_page: DashboardPageSummary
  events_page: DashboardPageSummary
  transitions: DashboardTransitionSummary[]
  events: DashboardEventSummary[]
}

export interface DashboardActiveRepositoriesResponse {
  active_repositories: string[]
}

export type DashboardView = 'snapshot' | 'controls'

export interface DashboardQueryState {
  limit: number
  offset: number
  entity_key: string
  job_id: string
  trace_id: string
  status: string
}

export interface DashboardRenderState {
  query: DashboardQueryState
  active_view: DashboardView
  selected_job_id: string | null
  timeline_offset: number
  selected_timeline_event_key: string | null
  transitions_collapsed: boolean
  events_collapsed: boolean
  anomalies_collapsed: boolean
  new_job_ids?: string[]
  new_transition_keys?: string[]
  new_event_keys?: string[]
  new_anomaly_keys?: string[]
  new_timeline_event_keys?: string[]
  has_pending_new_row_markers?: boolean
  is_background_refresh_in_flight?: boolean
  overview: DashboardOverviewResponse | null
  timeline: DashboardJobTimelineResponse | null
  active_repositories: string[]
  controls_is_loading: boolean
  controls_is_saving: boolean
  controls_error_message: string | null
  controls_feedback_message: string | null
  is_loading: boolean
  error_message: string | null
}

const DEFAULT_LIMIT = 20
const DEFAULT_OFFSET = 0
const DEFAULT_API_BASE_URL = 'http://localhost:8000'
const DEFAULT_AGENT1_POLL_INTERVAL_SECONDS = 30
const STATUS_OPTIONS = ['', 'ok', 'retry', 'blocked', 'error']
const POSITIVE_TONE_VALUES = new Set([
  'ok',
  'success',
  'succeeded',
  'completed',
  'ready_to_execute',
  'active'
])
const NEGATIVE_TONE_VALUES = new Set([
  'failure',
  'failed',
  'error',
  'blocked',
  'sev1',
  'sev2',
  'critical'
])
const WARNING_TONE_VALUES = new Set([
  'retry',
  'timeout',
  'pending',
  'awaiting_context',
  'awaiting_human_feedback',
  'executing'
])
const INFO_TONE_VALUES = new Set([
  'dev',
  'prod',
  'ci',
  'issue',
  'pr_author',
  'pr_reviewer',
  'shadow',
  'dry_run'
])

function createInitialRenderState(): DashboardRenderState {
  return {
    query: {
      limit: DEFAULT_LIMIT,
      offset: DEFAULT_OFFSET,
      entity_key: '',
      job_id: '',
      trace_id: '',
      status: ''
    },
    active_view: 'snapshot',
    selected_job_id: null,
    timeline_offset: DEFAULT_OFFSET,
    selected_timeline_event_key: null,
    transitions_collapsed: true,
    events_collapsed: true,
    anomalies_collapsed: true,
    new_job_ids: [],
    new_transition_keys: [],
    new_event_keys: [],
    new_anomaly_keys: [],
    new_timeline_event_keys: [],
    has_pending_new_row_markers: false,
    is_background_refresh_in_flight: false,
    overview: null,
    timeline: null,
    active_repositories: [],
    controls_is_loading: false,
    controls_is_saving: false,
    controls_error_message: null,
    controls_feedback_message: null,
    is_loading: true,
    error_message: null
  }
}

function escapeHtml(value: string): string {
  return value
    .replaceAll('&', '&amp;')
    .replaceAll('<', '&lt;')
    .replaceAll('>', '&gt;')
    .replaceAll('"', '&quot;')
    .replaceAll("'", '&#39;')
}

function resolveToneClassName(value: string): string {
  const normalizedValue = value.trim().toLowerCase()
  if (POSITIVE_TONE_VALUES.has(normalizedValue)) {
    return 'tone-success'
  }
  if (NEGATIVE_TONE_VALUES.has(normalizedValue)) {
    return 'tone-failure'
  }
  if (WARNING_TONE_VALUES.has(normalizedValue)) {
    return 'tone-warning'
  }
  if (INFO_TONE_VALUES.has(normalizedValue)) {
    return 'tone-info'
  }

  return 'tone-neutral'
}

function createToneMarkup(value: string): string {
  return `<span class='tone ${resolveToneClassName(value)}'>${escapeHtml(value)}</span>`
}

function formatDateTime(value: string): string {
  const parsedDate = new Date(value)
  if (Number.isNaN(parsedDate.valueOf())) {
    return value
  }

  return parsedDate.toISOString()
}

function toOptionalFilterValue(value: string): string | null {
  const normalized = value.trim()
  if (normalized === '') {
    return null
  }

  return normalized
}

function parseInteger(value: string, fallbackValue: number): number {
  const parsedValue = Number.parseInt(value, 10)
  if (Number.isNaN(parsedValue)) {
    return fallbackValue
  }

  if (parsedValue < 0) {
    return 0
  }

  return parsedValue
}

function hasPageNext(page: DashboardPageSummary): boolean {
  return page.offset + page.limit < page.total
}

function createTimelineEventKey(event: DashboardEventSummary): string {
  return [
    event.timestamp,
    event.trace_id,
    event.event_type,
    event.status
  ].join('|')
}

function createTransitionKey(transition: DashboardTransitionSummary): string {
  return [
    transition.job_id,
    transition.from_state,
    transition.to_state,
    transition.reason,
    transition.transition_at
  ].join('|')
}

function createAnomalyKey(anomaly: DashboardAnomalySummary): string {
  return [
    anomaly.timestamp,
    anomaly.trace_id,
    anomaly.job_id,
    anomaly.alert_name,
    anomaly.severity
  ].join('|')
}

function resolveNewKeys(previousKeys: string[], nextKeys: string[]): string[] {
  const previousKeySet = new Set(previousKeys)
  return nextKeys.filter((nextKey) => !previousKeySet.has(nextKey))
}

function clearNewRowMarkers(state: DashboardRenderState): void {
  state.new_job_ids = []
  state.new_transition_keys = []
  state.new_event_keys = []
  state.new_anomaly_keys = []
  state.new_timeline_event_keys = []
  state.has_pending_new_row_markers = false
}

function applyBackgroundRefreshRowMarkers(
  state: DashboardRenderState,
  previousOverview: DashboardOverviewResponse | null,
  nextOverview: DashboardOverviewResponse,
  previousTimeline: DashboardJobTimelineResponse | null,
  nextTimeline: DashboardJobTimelineResponse | null
): void {
  if (previousOverview === null) {
    clearNewRowMarkers(state)
    return
  }

  const previousJobIds = previousOverview.jobs.map((job) => job.job_id)
  const nextJobIds = nextOverview.jobs.map((job) => job.job_id)
  const previousTransitionKeys = previousOverview.transitions.map((transition) => createTransitionKey(transition))
  const nextTransitionKeys = nextOverview.transitions.map((transition) => createTransitionKey(transition))
  const previousEventKeys = previousOverview.events.map((event) => createTimelineEventKey(event))
  const nextEventKeys = nextOverview.events.map((event) => createTimelineEventKey(event))
  const previousAnomalyKeys = previousOverview.anomalies.map((anomaly) => createAnomalyKey(anomaly))
  const nextAnomalyKeys = nextOverview.anomalies.map((anomaly) => createAnomalyKey(anomaly))
  const previousTimelineEventKeys = previousTimeline === null
    ? []
    : previousTimeline.events.map((event) => createTimelineEventKey(event))
  const nextTimelineEventKeys = nextTimeline === null
    ? []
    : nextTimeline.events.map((event) => createTimelineEventKey(event))
  state.new_job_ids = resolveNewKeys(previousJobIds, nextJobIds)
  state.new_transition_keys = resolveNewKeys(previousTransitionKeys, nextTransitionKeys)
  state.new_event_keys = resolveNewKeys(previousEventKeys, nextEventKeys)
  state.new_anomaly_keys = resolveNewKeys(previousAnomalyKeys, nextAnomalyKeys)
  state.new_timeline_event_keys = resolveNewKeys(previousTimelineEventKeys, nextTimelineEventKeys)
  state.has_pending_new_row_markers = (
    state.new_job_ids.length > 0 ||
    state.new_transition_keys.length > 0 ||
    state.new_event_keys.length > 0 ||
    state.new_anomaly_keys.length > 0 ||
    state.new_timeline_event_keys.length > 0
  )
}

function createNewRowClassName(isNewRow: boolean): string {
  return isNewRow ? ' class=\'row-new\'' : ''
}

function arePayloadsEquivalent(leftPayload: unknown, rightPayload: unknown): boolean {
  return JSON.stringify(leftPayload) === JSON.stringify(rightPayload)
}

function getSelectedTimelineEvent(state: DashboardRenderState): DashboardEventSummary | null {
  if (state.timeline === null || state.selected_timeline_event_key === null) {
    return null
  }

  const selectedEvent = state.timeline.events.find((event) => (
    createTimelineEventKey(event) === state.selected_timeline_event_key
  ))
  return selectedEvent ?? null
}

function getTimelineEventReason(event: DashboardEventSummary): string | null {
  const rawReason = event.details.reason
  if (typeof rawReason !== 'string') {
    return null
  }

  const normalizedReason = rawReason.trim()
  if (normalizedReason === '') {
    return null
  }

  return normalizedReason
}

function toRecord(value: unknown): Record<string, unknown> | null {
  if (typeof value !== 'object' || value === null) {
    return null
  }

  return value as Record<string, unknown>
}

function getEventErrorSummary(event: DashboardEventSummary): string | null {
  const detailsRecord = toRecord(event.details)
  if (detailsRecord === null) {
    return null
  }
  const transitionDetailsRecord = toRecord(detailsRecord.transition_details)
  if (transitionDetailsRecord === null) {
    return null
  }

  const httpStatus = transitionDetailsRecord.http_status
  const errorMessage = transitionDetailsRecord.error_message
  const errorType = transitionDetailsRecord.error_type
  const codexSummary = transitionDetailsRecord.codex_summary
  const summarySegments: string[] = []
  if (typeof httpStatus === 'number') {
    summarySegments.push(`HTTP ${httpStatus}`)
  }
  if (typeof errorType === 'string' && errorType.trim() !== '') {
    summarySegments.push(errorType)
  }
  if (typeof codexSummary === 'string' && codexSummary.trim() !== '') {
    summarySegments.push(codexSummary.trim())
  }
  if (typeof errorMessage === 'string' && errorMessage.trim() !== '') {
    summarySegments.push(errorMessage.trim())
  }
  if (summarySegments.length === 0) {
    return null
  }

  return summarySegments.join(' - ')
}

function getSelectedEventErrorSummary(event: DashboardEventSummary): string | null {
  return getEventErrorSummary(event)
}

function formatEventDetails(details: Record<string, unknown>): string {
  return JSON.stringify(details, null, 2)
}

function isDashboardOverviewResponse(payload: unknown): payload is DashboardOverviewResponse {
  if (typeof payload !== 'object' || payload === null) {
    return false
  }

  const record = payload as Record<string, unknown>
  return (
    Array.isArray(record.jobs) &&
    Array.isArray(record.transitions) &&
    Array.isArray(record.events) &&
    Array.isArray(record.anomalies) &&
    typeof record.jobs_page === 'object' &&
    record.jobs_page !== null &&
    typeof record.transitions_page === 'object' &&
    record.transitions_page !== null &&
    typeof record.events_page === 'object' &&
    record.events_page !== null &&
    typeof record.anomalies_page === 'object' &&
    record.anomalies_page !== null &&
    typeof record.filters === 'object' &&
    record.filters !== null
  )
}

function isDashboardJobTimelineResponse(payload: unknown): payload is DashboardJobTimelineResponse {
  if (typeof payload !== 'object' || payload === null) {
    return false
  }

  const record = payload as Record<string, unknown>
  return (
    typeof record.job === 'object' &&
    record.job !== null &&
    Array.isArray(record.transitions) &&
    Array.isArray(record.events) &&
    typeof record.transitions_page === 'object' &&
    record.transitions_page !== null &&
    typeof record.events_page === 'object' &&
    record.events_page !== null
  )
}

function isDashboardActiveRepositoriesResponse(
  payload: unknown
): payload is DashboardActiveRepositoriesResponse {
  if (typeof payload !== 'object' || payload === null) {
    return false
  }

  const record = payload as Record<string, unknown>
  if (!Array.isArray(record.active_repositories)) {
    return false
  }

  return record.active_repositories.every((repository) => typeof repository === 'string')
}

function createRows(items: string[], emptyMessage: string, columnCount: number): string {
  if (items.length === 0) {
    return `<tr><td colspan='${escapeHtml(String(columnCount))}' class='empty-row'>${escapeHtml(emptyMessage)}</td></tr>`
  }

  return items.join('')
}

function createFilterControlsMarkup(state: DashboardRenderState): string {
  const selectedStatusOptions = STATUS_OPTIONS.map((option) => {
    const selectedAttribute = state.query.status === option ? ' selected' : ''
    const optionLabel = option === '' ? 'Any status' : option
    return `<option value='${escapeHtml(option)}'${selectedAttribute}>${escapeHtml(optionLabel)}</option>`
  }).join('')

  return `
    <section class='table-section'>
      <h2>Filters</h2>
      <form id='filters-form' class='filters-grid'>
        <label>Entity Key
          <input id='filter-entity-key' type='text' value='${escapeHtml(state.query.entity_key)}' placeholder='Vaquum/Agent1#123'>
        </label>
        <label>Job ID
          <input id='filter-job-id' type='text' value='${escapeHtml(state.query.job_id)}' placeholder='job_abc'>
        </label>
        <label>Trace ID
          <input id='filter-trace-id' type='text' value='${escapeHtml(state.query.trace_id)}' placeholder='trc_abc'>
        </label>
        <label>Status
          <select id='filter-status'>${selectedStatusOptions}</select>
        </label>
        <label>Limit
          <input id='filter-limit' type='number' min='1' max='200' value='${escapeHtml(String(state.query.limit))}'>
        </label>
        <div class='filter-actions'>
          <button type='submit' class='button-primary'>Apply</button>
          <button type='button' id='filters-clear' class='button-secondary'>Clear</button>
        </div>
      </form>
    </section>
  `
}

function createNavigationMarkup(state: DashboardRenderState, statusText: string): string {
  const snapshotButtonClassName = state.active_view === 'snapshot'
    ? 'nav-link nav-link-active'
    : 'nav-link'
  const controlsButtonClassName = state.active_view === 'controls'
    ? 'nav-link nav-link-active'
    : 'nav-link'

  return `
    <section class='navigation-shell'>
      <nav class='navigation-menu'>
        <button type='button' id='nav-snapshot' class='${escapeHtml(snapshotButtonClassName)}'>SNAPSHOT</button>
        <button type='button' id='nav-controls' class='${escapeHtml(controlsButtonClassName)}'>CONTROLS</button>
      </nav>
      <p class='status'>${escapeHtml(statusText)}</p>
    </section>
  `
}

function createControlsSectionMarkup(state: DashboardRenderState): string {
  const controlsStatusMessages: string[] = []
  if (state.controls_is_loading) {
    controlsStatusMessages.push('Loading current repository allow list...')
  }
  if (state.controls_is_saving) {
    controlsStatusMessages.push('Saving control update...')
  }
  if (state.controls_error_message !== null) {
    controlsStatusMessages.push(state.controls_error_message)
  }
  if (state.controls_feedback_message !== null) {
    controlsStatusMessages.push(state.controls_feedback_message)
  }
  const controlsStatusMarkup = controlsStatusMessages.length === 0
    ? '<p class=\'status\'>Manage repositories that Agent1 is allowed to operate on.</p>'
    : controlsStatusMessages.map((message) => (
      `<p class='status'>${escapeHtml(message)}</p>`
    )).join('')
  const repositoryItems = state.active_repositories.map((repository) => {
    const removeDisabledAttribute = state.active_repositories.length <= 1 || state.controls_is_saving
      ? ' disabled'
      : ''
    return `
      <li class='repository-allow-item'>
        <span class='repository-allow-name'>${escapeHtml(repository)}</span>
        <button
          type='button'
          class='button-secondary remove-repository'
          data-repository='${escapeHtml(repository)}'${removeDisabledAttribute}
        >
          Remove
        </button>
      </li>
    `
  }).join('')
  const emptyStateMarkup = repositoryItems === ''
    ? '<li class=\'repository-allow-empty\'>No repositories configured.</li>'
    : repositoryItems

  return `
    <section class='table-section controls-section'>
      <h2>Repository Allow List</h2>
      ${controlsStatusMarkup}
      <form id='controls-add-form' class='controls-add-form'>
        <label>Repository
          <input id='controls-repository-input' type='text' placeholder='Vaquum/Agent1'>
        </label>
        <div class='controls-actions'>
          <button type='submit' class='button-primary'${state.controls_is_saving ? ' disabled' : ''}>Add</button>
          <button type='button' id='controls-refresh' class='button-secondary'${state.controls_is_loading ? ' disabled' : ''}>Reload</button>
        </div>
      </form>
      <ul class='repository-allow-list'>
        ${emptyStateMarkup}
      </ul>
    </section>
  `
}

function createPageControlsMarkup(prefix: string, page: DashboardPageSummary): string {
  const previousDisabled = page.offset <= 0 ? ' disabled' : ''
  const nextDisabled = hasPageNext(page) ? '' : ' disabled'
  const start = page.total === 0 ? 0 : page.offset + 1
  const end = Math.min(page.offset + page.limit, page.total)

  return `
    <div class='page-controls'>
      <button type='button' id='${escapeHtml(prefix)}-prev' class='button-secondary'${previousDisabled}>Previous</button>
      <button type='button' id='${escapeHtml(prefix)}-next' class='button-secondary'${nextDisabled}>Next</button>
      <span>${escapeHtml(String(start))}-${escapeHtml(String(end))} of ${escapeHtml(String(page.total))}</span>
    </div>
  `
}

type CollapsibleSection = 'transitions' | 'events' | 'anomalies'

function createSectionHeaderMarkup(
  title: string,
  sectionName: CollapsibleSection,
  isCollapsed: boolean
): string {
  const isExpanded = !isCollapsed
  return `
    <div class='table-section-header'>
      <h2>${escapeHtml(title)}</h2>
      <button
        type='button'
        class='section-toggle'
        data-section='${escapeHtml(sectionName)}'
        aria-expanded='${escapeHtml(String(isExpanded))}'
      >
        <span class='section-toggle-arrow'>▾</span>
      </button>
    </div>
  `
}

function createJobRowsMarkup(state: DashboardRenderState, jobs: DashboardJobSummary[]): string {
  if (jobs.length === 0) {
    return `<tr><td colspan='9' class='empty-row'>No jobs recorded.</td></tr>`
  }

  const rows: string[] = []
  for (const job of jobs) {
    const isTimelineExpanded = state.selected_job_id === job.job_id
    const isNewJobRow = (state.new_job_ids ?? []).includes(job.job_id)
    const jobRowClassName = createNewRowClassName(isNewJobRow)
    rows.push(`
      <tr${jobRowClassName}>
        <td>
          <button
            type='button'
            class='button-secondary toggle-job-timeline'
            data-testid='toggle-job-timeline'
            data-job-id='${escapeHtml(job.job_id)}'
          >
            ${isTimelineExpanded ? '-' : '+'}
          </button>
        </td>
        <td data-testid='job-id-cell'>${escapeHtml(job.job_id)}</td>
        <td>${escapeHtml(job.entity_key)}</td>
        <td>${createToneMarkup(job.kind)}</td>
        <td>${createToneMarkup(job.state)}</td>
        <td>${createToneMarkup(job.environment)}</td>
        <td>${createToneMarkup(job.mode)}</td>
        <td>${escapeHtml(String(job.lease_epoch))}</td>
        <td>${escapeHtml(formatDateTime(job.updated_at))}</td>
      </tr>
    `)
    if (!isTimelineExpanded) {
      continue
    }

    if (state.timeline === null || state.timeline.job.job_id !== job.job_id) {
      rows.push(`
        <tr class='nested-row timeline-row'>
          <td></td>
          <td colspan='8' class='nested-level-1'>
            Loading timeline for ${escapeHtml(job.job_id)}...
          </td>
        </tr>
      `)
      continue
    }

    if (state.timeline.events.length === 0) {
      rows.push(`
        <tr class='nested-row timeline-row'>
          <td></td>
          <td colspan='8' class='nested-level-1'>
            No timeline events recorded for this job.
          </td>
        </tr>
      `)
      continue
    }

    rows.push(`
      <tr class='nested-row timeline-row timeline-header-row'>
        <td></td>
        <td colspan='8' class='nested-level-1'>
          Timeline events (${escapeHtml(String(state.timeline.events.length))})
        </td>
      </tr>
    `)

    for (const timelineEvent of state.timeline.events) {
      const eventKey = createTimelineEventKey(timelineEvent)
      const isEventExpanded = state.selected_timeline_event_key === eventKey
      const eventReason = getTimelineEventReason(timelineEvent)
      const isNewTimelineEventRow = (state.new_timeline_event_keys ?? []).includes(eventKey)
      rows.push(`
        <tr class='nested-row timeline-row${isNewTimelineEventRow ? ' row-new' : ''}'>
          <td>
            <button
              type='button'
              class='button-secondary toggle-timeline-event'
              data-testid='toggle-timeline-event'
              data-event-key='${escapeHtml(eventKey)}'
            >
              ${isEventExpanded ? '-' : '+'}
            </button>
          </td>
          <td class='nested-level-1'>${escapeHtml(timelineEvent.event_type)}</td>
          <td>${escapeHtml(formatDateTime(timelineEvent.timestamp))}</td>
          <td>${escapeHtml(timelineEvent.trace_id)}</td>
          <td>${escapeHtml(timelineEvent.source)}</td>
          <td>${createToneMarkup(timelineEvent.status)}</td>
          <td>${escapeHtml(eventReason ?? '')}</td>
          <td colspan='2'></td>
        </tr>
      `)
      if (!isEventExpanded) {
        continue
      }

      const selectedEventErrorSummary = getSelectedEventErrorSummary(timelineEvent)
      const correlatedTransitions = eventReason === null
        ? []
        : state.timeline.transitions.filter((transition) => transition.reason === eventReason)
      const correlatedTransitionsMarkup = correlatedTransitions.length === 0
        ? '<li>No correlated transitions found for selected event.</li>'
        : correlatedTransitions.map((transition) => (
          `<li>${escapeHtml(transition.from_state)} → ${escapeHtml(transition.to_state)} · ${escapeHtml(transition.reason)} · ${escapeHtml(formatDateTime(transition.transition_at))}</li>`
        )).join('')
      rows.push(`
        <tr class='nested-row inspection-row'>
          <td></td>
          <td colspan='8' class='nested-level-2'>
            <div class='event-details-panel'>
              <h3>Timeline Event Inspection</h3>
              <p class='status'>
                Trace ${escapeHtml(timelineEvent.trace_id)} at ${escapeHtml(formatDateTime(timelineEvent.timestamp))}
              </p>
              ${selectedEventErrorSummary === null
                ? ''
                : `<p class='status status-error'>${escapeHtml(selectedEventErrorSummary)}</p>`
              }
              <button
                type='button'
                class='button-secondary apply-trace-filter'
                data-testid='apply-trace-filter'
                data-trace-id='${escapeHtml(timelineEvent.trace_id)}'
              >
                Filter Overview by Trace
              </button>
              <pre class='event-details-json'>${escapeHtml(formatEventDetails(timelineEvent.details))}</pre>
              <h3>Correlated Transitions</h3>
              <ul class='event-transition-list'>
                ${correlatedTransitionsMarkup}
              </ul>
            </div>
          </td>
        </tr>
      `)
    }
  }

  return rows.join('')
}

function createSnapshotMarkup(state: DashboardRenderState): string {
  const overview = state.overview
  const jobs = overview?.jobs ?? []
  const transitions = overview?.transitions ?? []
  const events = overview?.events ?? []
  const anomalies = overview?.anomalies ?? []
  const jobsRows = createJobRowsMarkup(state, jobs)
  const transitionRows = createRows(
    transitions.map((transition) => {
      const transitionKey = createTransitionKey(transition)
      const isNewTransitionRow = (state.new_transition_keys ?? []).includes(transitionKey)
      const transitionRowClassName = createNewRowClassName(isNewTransitionRow)
      return (
      `<tr${transitionRowClassName}>
        <td>${escapeHtml(transition.job_id)}</td>
        <td>${createToneMarkup(transition.from_state)}</td>
        <td>${createToneMarkup(transition.to_state)}</td>
        <td>${escapeHtml(transition.reason)}</td>
        <td>${escapeHtml(formatDateTime(transition.transition_at))}</td>
      </tr>`
      )
    }),
    'No transitions recorded.',
    5
  )
  const eventRows = createRows(
    events.map((event) => {
      const eventKey = createTimelineEventKey(event)
      const isNewEventRow = (state.new_event_keys ?? []).includes(eventKey)
      const eventRowClassName = createNewRowClassName(isNewEventRow)
      return (
      `<tr${eventRowClassName}>
        <td>${escapeHtml(formatDateTime(event.timestamp))}</td>
        <td data-testid='overview-trace-cell'>${escapeHtml(event.trace_id)}</td>
        <td>${escapeHtml(event.job_id)}</td>
        <td>${escapeHtml(event.entity_key)}</td>
        <td>${escapeHtml(event.source)}</td>
        <td>${escapeHtml(event.event_type)}</td>
        <td>${createToneMarkup(event.status)}</td>
      </tr>`
      )
    }),
    'No events recorded.',
    7
  )
  const anomalyRows = createRows(
    anomalies.map((anomaly) => {
      const anomalyKey = createAnomalyKey(anomaly)
      const isNewAnomalyRow = (state.new_anomaly_keys ?? []).includes(anomalyKey)
      const anomalyRowClassName = createNewRowClassName(isNewAnomalyRow)
      return (
      `<tr${anomalyRowClassName}>
        <td>${escapeHtml(formatDateTime(anomaly.timestamp))}</td>
        <td>${escapeHtml(anomaly.alert_name)}</td>
        <td>${createToneMarkup(anomaly.severity)}</td>
        <td>${escapeHtml(anomaly.trace_id)}</td>
        <td>${escapeHtml(anomaly.job_id)}</td>
        <td>${escapeHtml(anomaly.runbook)}</td>
      </tr>`
      )
    }),
    'No anomalies detected.',
    6
  )
  const jobsTotal = overview?.jobs_page.total ?? 0
  const transitionsTotal = overview?.transitions_page.total ?? 0
  const eventsTotal = overview?.events_page.total ?? 0
  const anomaliesTotal = overview?.anomalies_page.total ?? 0

  return `
      ${createFilterControlsMarkup(state)}
      <section class='metrics'>
        <article class='metric-card'><h2>Jobs</h2><p>${escapeHtml(String(jobsTotal))}</p></article>
        <article class='metric-card'><h2>Transitions</h2><p>${escapeHtml(String(transitionsTotal))}</p></article>
        <article class='metric-card'><h2>Events</h2><p>${escapeHtml(String(eventsTotal))}</p></article>
        <article class='metric-card'><h2>Anomalies</h2><p>${escapeHtml(String(anomaliesTotal))}</p></article>
      </section>
      <section class='table-section'>
        <h2>Recent Jobs</h2>
        ${overview ? createPageControlsMarkup('overview', overview.jobs_page) : ''}
        <table>
          <thead>
            <tr><th>Action</th><th>Job</th><th>Entity</th><th>Kind</th><th>State</th><th>Env</th><th>Mode</th><th>Lease</th><th>Updated</th></tr>
          </thead>
          <tbody>${jobsRows}</tbody>
        </table>
      </section>
      <section class='table-section'>
        ${createSectionHeaderMarkup('Recent Transitions', 'transitions', state.transitions_collapsed)}
        ${state.transitions_collapsed
          ? ''
          : `
            ${overview ? `<p class='status'>Filtered count: ${escapeHtml(String(overview.transitions_page.total))}</p>` : ''}
            <table>
              <thead>
                <tr><th>Job</th><th>From</th><th>To</th><th>Reason</th><th>At</th></tr>
              </thead>
              <tbody>${transitionRows}</tbody>
            </table>
          `
        }
      </section>
      <section class='table-section'>
        ${createSectionHeaderMarkup('Recent Events', 'events', state.events_collapsed)}
        ${state.events_collapsed
          ? ''
          : `
            ${overview ? `<p class='status'>Filtered count: ${escapeHtml(String(overview.events_page.total))}</p>` : ''}
            <table>
              <thead>
                <tr><th>Timestamp</th><th>Trace</th><th>Job</th><th>Entity</th><th>Source</th><th>Type</th><th>Status</th></tr>
              </thead>
              <tbody>${eventRows}</tbody>
            </table>
          `
        }
      </section>
      <section class='table-section'>
        ${createSectionHeaderMarkup('Recent Anomalies', 'anomalies', state.anomalies_collapsed)}
        ${state.anomalies_collapsed
          ? ''
          : `
            ${overview ? `<p class='status'>Filtered count: ${escapeHtml(String(overview.anomalies_page.total))}</p>` : ''}
            <table>
              <thead>
                <tr><th>Timestamp</th><th>Alert</th><th>Severity</th><th>Trace</th><th>Job</th><th>Runbook</th></tr>
              </thead>
              <tbody>${anomalyRows}</tbody>
            </table>
          `
        }
      </section>
  `
}

export function createDashboardMarkup(state: DashboardRenderState): string {
  const statusText = state.error_message ?? (state.is_loading ? 'Snapshot syncing...' : 'Snapshot ready')
  const viewMarkup = state.active_view === 'controls'
    ? createControlsSectionMarkup(state)
    : createSnapshotMarkup(state)

  return `
    <main class='layout'>
      ${createNavigationMarkup(state, statusText)}
      ${viewMarkup}
    </main>
  `
}

function getDashboardAutoRefreshIntervalMs(): number {
  const configuredSeconds = Number.parseInt(
    (import.meta.env.VITE_AGENT1_POLL_INTERVAL_SECONDS as string | undefined) ?? '',
    10
  )
  const resolvedSeconds = Number.isNaN(configuredSeconds) || configuredSeconds <= 0
    ? DEFAULT_AGENT1_POLL_INTERVAL_SECONDS
    : configuredSeconds
  return resolvedSeconds * 1000
}

function shouldPauseBackgroundRefresh(): boolean {
  if (typeof document === 'undefined') {
    return false
  }
  const activeElement = document.activeElement
  return (
    activeElement instanceof HTMLInputElement ||
    activeElement instanceof HTMLSelectElement ||
    activeElement instanceof HTMLTextAreaElement
  )
}

function getApiBaseUrl(): string {
  const configuredApiBaseUrl = (import.meta.env.VITE_AGENT1_API_BASE_URL as string | undefined) ?? ''
  return configuredApiBaseUrl.trim() === ''
    ? DEFAULT_API_BASE_URL
    : configuredApiBaseUrl.trim()
}

function createOverviewRequestUrl(query: DashboardQueryState): string {
  const searchParams = new URLSearchParams()
  searchParams.set('limit', String(query.limit))
  searchParams.set('offset', String(query.offset))
  const entityKey = toOptionalFilterValue(query.entity_key)
  const jobId = toOptionalFilterValue(query.job_id)
  const traceId = toOptionalFilterValue(query.trace_id)
  const status = toOptionalFilterValue(query.status)
  if (entityKey !== null) {
    searchParams.set('entity_key', entityKey)
  }
  if (jobId !== null) {
    searchParams.set('job_id', jobId)
  }
  if (traceId !== null) {
    searchParams.set('trace_id', traceId)
  }
  if (status !== null) {
    searchParams.set('status', status)
  }

  return `${getApiBaseUrl()}/dashboard/overview?${searchParams.toString()}`
}

function createTimelineRequestUrl(jobId: string, limit: number, offset: number): string {
  const searchParams = new URLSearchParams()
  searchParams.set('limit', String(limit))
  searchParams.set('offset', String(offset))
  return `${getApiBaseUrl()}/dashboard/jobs/${encodeURIComponent(jobId)}/timeline?${searchParams.toString()}`
}

function createActiveRepositoriesRequestUrl(): string {
  return `${getApiBaseUrl()}/dashboard/controls/active-repositories`
}

async function fetchDashboardOverview(query: DashboardQueryState): Promise<DashboardOverviewResponse> {
  const requestUrl = createOverviewRequestUrl(query)
  const response = await fetch(requestUrl)
  if (!response.ok) {
    throw new Error(`Dashboard API request failed with status ${response.status}`)
  }

  const payload: unknown = await response.json()
  if (!isDashboardOverviewResponse(payload)) {
    throw new Error('Dashboard API returned an invalid payload shape.')
  }

  return payload
}

async function fetchDashboardTimeline(
  jobId: string,
  limit: number,
  offset: number
): Promise<DashboardJobTimelineResponse> {
  const requestUrl = createTimelineRequestUrl(jobId, limit, offset)
  const response = await fetch(requestUrl)
  if (!response.ok) {
    throw new Error(`Dashboard timeline request failed with status ${response.status}`)
  }

  const payload: unknown = await response.json()
  if (!isDashboardJobTimelineResponse(payload)) {
    throw new Error('Dashboard timeline API returned an invalid payload shape.')
  }

  return payload
}

async function fetchDashboardActiveRepositories(): Promise<DashboardActiveRepositoriesResponse> {
  const requestUrl = createActiveRepositoriesRequestUrl()
  const response = await fetch(requestUrl)
  if (!response.ok) {
    throw new Error(`Dashboard controls request failed with status ${response.status}`)
  }

  const payload: unknown = await response.json()
  if (!isDashboardActiveRepositoriesResponse(payload)) {
    throw new Error('Dashboard controls API returned an invalid payload shape.')
  }

  return payload
}

async function updateDashboardActiveRepositories(
  activeRepositories: string[]
): Promise<DashboardActiveRepositoriesResponse> {
  const requestUrl = createActiveRepositoriesRequestUrl()
  const response = await fetch(requestUrl, {
    method: 'PUT',
    headers: {
      'Content-Type': 'application/json'
    },
    body: JSON.stringify({
      active_repositories: activeRepositories
    })
  })
  if (!response.ok) {
    throw new Error(`Dashboard controls update failed with status ${response.status}`)
  }

  const payload: unknown = await response.json()
  if (!isDashboardActiveRepositoriesResponse(payload)) {
    throw new Error('Dashboard controls update API returned an invalid payload shape.')
  }

  return payload
}

function getErrorMessage(error: unknown): string {
  if (error instanceof Error) {
    return error.message
  }

  return 'Failed to load dashboard snapshot.'
}

function normalizeRepositoryScopeValue(value: string): string {
  return value.trim()
}

function isValidRepositoryScopeValue(value: string): boolean {
  const normalizedValue = normalizeRepositoryScopeValue(value)
  const repositorySegments = normalizedValue.split('/')
  if (repositorySegments.length !== 2) {
    return false
  }

  return repositorySegments.every((segment) => segment.trim() !== '')
}

function bindDashboardControls(
  app: HTMLDivElement,
  state: DashboardRenderState,
  refreshOverview: () => Promise<void>,
  refreshTimeline: () => Promise<void>,
  refreshControls: () => Promise<void>,
  saveControls: (activeRepositories: string[]) => Promise<void>
): void {
  const snapshotNavigationButton = app.querySelector<HTMLButtonElement>('#nav-snapshot')
  if (snapshotNavigationButton !== null) {
    snapshotNavigationButton.addEventListener('click', () => {
      if (state.active_view === 'snapshot') {
        return
      }

      state.active_view = 'snapshot'
      renderDashboard(
        app,
        state,
        refreshOverview,
        refreshTimeline,
        refreshControls,
        saveControls
      )
    })
  }

  const controlsNavigationButton = app.querySelector<HTMLButtonElement>('#nav-controls')
  if (controlsNavigationButton !== null) {
    controlsNavigationButton.addEventListener('click', () => {
      if (state.active_view === 'controls') {
        return
      }

      state.active_view = 'controls'
      renderDashboard(
        app,
        state,
        refreshOverview,
        refreshTimeline,
        refreshControls,
        saveControls
      )
      void refreshControls()
    })
  }

  const filtersForm = app.querySelector<HTMLFormElement>('#filters-form')
  if (filtersForm !== null) {
    filtersForm.addEventListener('submit', (event) => {
      event.preventDefault()
      const entityInput = app.querySelector<HTMLInputElement>('#filter-entity-key')
      const jobInput = app.querySelector<HTMLInputElement>('#filter-job-id')
      const traceInput = app.querySelector<HTMLInputElement>('#filter-trace-id')
      const statusInput = app.querySelector<HTMLSelectElement>('#filter-status')
      const limitInput = app.querySelector<HTMLInputElement>('#filter-limit')
      state.query.entity_key = entityInput?.value ?? ''
      state.query.job_id = jobInput?.value ?? ''
      state.query.trace_id = traceInput?.value ?? ''
      state.query.status = statusInput?.value ?? ''
      state.query.limit = parseInteger(limitInput?.value ?? String(DEFAULT_LIMIT), DEFAULT_LIMIT)
      if (state.query.limit <= 0) {
        state.query.limit = DEFAULT_LIMIT
      }
      if (state.query.limit > 200) {
        state.query.limit = 200
      }
      state.query.offset = DEFAULT_OFFSET
      state.timeline_offset = DEFAULT_OFFSET
      state.selected_job_id = null
      state.timeline = null
      state.selected_timeline_event_key = null
      state.active_view = 'snapshot'
      void refreshOverview()
    })
  }

  const clearButton = app.querySelector<HTMLButtonElement>('#filters-clear')
  if (clearButton !== null) {
    clearButton.addEventListener('click', () => {
      state.query.entity_key = ''
      state.query.job_id = ''
      state.query.trace_id = ''
      state.query.status = ''
      state.query.limit = DEFAULT_LIMIT
      state.query.offset = DEFAULT_OFFSET
      state.timeline_offset = DEFAULT_OFFSET
      state.selected_job_id = null
      state.timeline = null
      state.selected_timeline_event_key = null
      state.active_view = 'snapshot'
      void refreshOverview()
    })
  }

  const previousOverviewButton = app.querySelector<HTMLButtonElement>('#overview-prev')
  if (previousOverviewButton !== null) {
    previousOverviewButton.addEventListener('click', () => {
      if (state.query.offset <= 0) {
        return
      }

      state.query.offset = Math.max(0, state.query.offset - state.query.limit)
      void refreshOverview()
    })
  }

  const nextOverviewButton = app.querySelector<HTMLButtonElement>('#overview-next')
  if (nextOverviewButton !== null) {
    nextOverviewButton.addEventListener('click', () => {
      if (state.overview === null || !hasPageNext(state.overview.jobs_page)) {
        return
      }

      state.query.offset = state.query.offset + state.query.limit
      void refreshOverview()
    })
  }

  app.querySelectorAll<HTMLButtonElement>('button.toggle-job-timeline').forEach((button) => {
    button.addEventListener('click', () => {
      const jobId = button.dataset.jobId ?? ''
      if (jobId.trim() === '') {
        return
      }

      if (state.selected_job_id === jobId) {
        state.selected_job_id = null
        state.timeline = null
        state.selected_timeline_event_key = null
        state.timeline_offset = DEFAULT_OFFSET
        renderDashboard(
          app,
          state,
          refreshOverview,
          refreshTimeline,
          refreshControls,
          saveControls
        )
        return
      }

      state.selected_job_id = jobId
      state.timeline_offset = DEFAULT_OFFSET
      state.timeline = null
      state.selected_timeline_event_key = null
      state.error_message = null
      state.active_view = 'snapshot'
      renderDashboard(
        app,
        state,
        refreshOverview,
        refreshTimeline,
        refreshControls,
        saveControls
      )
      void refreshTimeline()
    })
  })

  app.querySelectorAll<HTMLButtonElement>('button.toggle-timeline-event').forEach((button) => {
    button.addEventListener('click', () => {
      const eventKey = button.dataset.eventKey ?? ''
      if (eventKey.trim() === '') {
        return
      }

      if (state.selected_timeline_event_key === eventKey) {
        state.selected_timeline_event_key = null
      } else {
        state.selected_timeline_event_key = eventKey
      }
      renderDashboard(
        app,
        state,
        refreshOverview,
        refreshTimeline,
        refreshControls,
        saveControls
      )
    })
  })

  app.querySelectorAll<HTMLButtonElement>('button.apply-trace-filter').forEach((button) => {
    button.addEventListener('click', () => {
      const traceId = button.dataset.traceId ?? ''
      if (traceId.trim() === '') {
        return
      }

      state.query.trace_id = traceId
      state.query.offset = DEFAULT_OFFSET
      state.timeline_offset = DEFAULT_OFFSET
      state.selected_timeline_event_key = null
      state.active_view = 'snapshot'
      void refreshOverview()
    })
  })

  app.querySelectorAll<HTMLButtonElement>('button.section-toggle').forEach((button) => {
    button.addEventListener('click', () => {
      const section = button.dataset.section ?? ''
      if (section === 'transitions') {
        state.transitions_collapsed = !state.transitions_collapsed
      } else if (section === 'events') {
        state.events_collapsed = !state.events_collapsed
      } else if (section === 'anomalies') {
        state.anomalies_collapsed = !state.anomalies_collapsed
      } else {
        return
      }
      renderDashboard(
        app,
        state,
        refreshOverview,
        refreshTimeline,
        refreshControls,
        saveControls
      )
    })
  })

  const previousTimelineButton = app.querySelector<HTMLButtonElement>('#timeline-prev')
  if (previousTimelineButton !== null) {
    previousTimelineButton.addEventListener('click', () => {
      if (state.timeline_offset <= 0) {
        return
      }

      state.timeline_offset = Math.max(0, state.timeline_offset - state.query.limit)
      void refreshTimeline()
    })
  }

  const nextTimelineButton = app.querySelector<HTMLButtonElement>('#timeline-next')
  if (nextTimelineButton !== null) {
    nextTimelineButton.addEventListener('click', () => {
      if (state.timeline === null) {
        return
      }

      const timelinePageSummary: DashboardPageSummary = {
        limit: state.timeline.transitions_page.limit,
        offset: state.timeline.transitions_page.offset,
        total: Math.max(state.timeline.transitions_page.total, state.timeline.events_page.total)
      }
      if (!hasPageNext(timelinePageSummary)) {
        return
      }

      state.timeline_offset = state.timeline_offset + state.query.limit
      void refreshTimeline()
    })
  }

  const controlsAddForm = app.querySelector<HTMLFormElement>('#controls-add-form')
  if (controlsAddForm !== null) {
    controlsAddForm.addEventListener('submit', (event) => {
      event.preventDefault()
      const controlsRepositoryInput = app.querySelector<HTMLInputElement>('#controls-repository-input')
      const repositoryScopeValue = controlsRepositoryInput?.value ?? ''
      const normalizedRepositoryScopeValue = normalizeRepositoryScopeValue(repositoryScopeValue)
      if (!isValidRepositoryScopeValue(normalizedRepositoryScopeValue)) {
        state.controls_error_message = 'Repository must use <owner>/<repo> format.'
        state.controls_feedback_message = null
        renderDashboard(
          app,
          state,
          refreshOverview,
          refreshTimeline,
          refreshControls,
          saveControls
        )
        return
      }
      if (state.active_repositories.includes(normalizedRepositoryScopeValue)) {
        state.controls_error_message = `Repository already allowed: ${normalizedRepositoryScopeValue}`
        state.controls_feedback_message = null
        renderDashboard(
          app,
          state,
          refreshOverview,
          refreshTimeline,
          refreshControls,
          saveControls
        )
        return
      }

      const nextActiveRepositories = [
        ...state.active_repositories,
        normalizedRepositoryScopeValue
      ]
      state.controls_error_message = null
      state.controls_feedback_message = null
      void saveControls(nextActiveRepositories)
    })
  }

  const controlsRefreshButton = app.querySelector<HTMLButtonElement>('#controls-refresh')
  if (controlsRefreshButton !== null) {
    controlsRefreshButton.addEventListener('click', () => {
      state.controls_error_message = null
      state.controls_feedback_message = null
      void refreshControls()
    })
  }

  app.querySelectorAll<HTMLButtonElement>('button.remove-repository').forEach((button) => {
    button.addEventListener('click', () => {
      const repository = button.dataset.repository ?? ''
      if (repository.trim() === '') {
        return
      }

      const nextActiveRepositories = state.active_repositories.filter(
        (repositoryScope) => repositoryScope !== repository
      )
      if (nextActiveRepositories.length === 0) {
        state.controls_error_message = 'At least one repository must remain in the allow list.'
        state.controls_feedback_message = null
        renderDashboard(
          app,
          state,
          refreshOverview,
          refreshTimeline,
          refreshControls,
          saveControls
        )
        return
      }

      state.controls_error_message = null
      state.controls_feedback_message = null
      void saveControls(nextActiveRepositories)
    })
  })
}

function renderDashboard(
  app: HTMLDivElement,
  state: DashboardRenderState,
  refreshOverview: () => Promise<void>,
  refreshTimeline: () => Promise<void>,
  refreshControls: () => Promise<void>,
  saveControls: (activeRepositories: string[]) => Promise<void>
): void {
  app.innerHTML = createDashboardMarkup(state)
  bindDashboardControls(
    app,
    state,
    refreshOverview,
    refreshTimeline,
    refreshControls,
    saveControls
  )
  if (state.has_pending_new_row_markers) {
    clearNewRowMarkers(state)
  }
}

async function startDashboard(app: HTMLDivElement): Promise<void> {
  const state = createInitialRenderState()

  async function refreshControls(): Promise<void> {
    state.controls_is_loading = true
    state.controls_error_message = null
    renderDashboard(
      app,
      state,
      refreshOverview,
      refreshTimeline,
      refreshControls,
      saveControls
    )
    try {
      const controlsPayload = await fetchDashboardActiveRepositories()
      state.active_repositories = controlsPayload.active_repositories
      state.controls_feedback_message = null
    } catch (error) {
      state.controls_error_message = getErrorMessage(error)
    } finally {
      state.controls_is_loading = false
      renderDashboard(
        app,
        state,
        refreshOverview,
        refreshTimeline,
        refreshControls,
        saveControls
      )
    }
  }

  async function saveControls(activeRepositories: string[]): Promise<void> {
    state.controls_is_saving = true
    state.controls_error_message = null
    state.controls_feedback_message = null
    renderDashboard(
      app,
      state,
      refreshOverview,
      refreshTimeline,
      refreshControls,
      saveControls
    )
    try {
      const controlsPayload = await updateDashboardActiveRepositories(activeRepositories)
      state.active_repositories = controlsPayload.active_repositories
      state.controls_feedback_message = 'Repository allow list updated.'
    } catch (error) {
      state.controls_error_message = getErrorMessage(error)
    } finally {
      state.controls_is_saving = false
      renderDashboard(
        app,
        state,
        refreshOverview,
        refreshTimeline,
        refreshControls,
        saveControls
      )
    }
  }

  async function refreshOverview(): Promise<void> {
    clearNewRowMarkers(state)
    state.is_loading = true
    state.error_message = null
    renderDashboard(
      app,
      state,
      refreshOverview,
      refreshTimeline,
      refreshControls,
      saveControls
    )
    try {
      state.overview = await fetchDashboardOverview(state.query)
    } catch (error) {
      state.overview = null
      state.timeline = null
      state.error_message = getErrorMessage(error)
    } finally {
      state.is_loading = false
      renderDashboard(
        app,
        state,
        refreshOverview,
        refreshTimeline,
        refreshControls,
        saveControls
      )
    }

    if (state.selected_job_id !== null && state.error_message === null) {
      await refreshTimeline()
    }
  }

  async function refreshTimeline(): Promise<void> {
    clearNewRowMarkers(state)
    if (state.selected_job_id === null) {
      state.timeline = null
      renderDashboard(
        app,
        state,
        refreshOverview,
        refreshTimeline,
        refreshControls,
        saveControls
      )
      return
    }

    try {
      state.timeline = await fetchDashboardTimeline(
        state.selected_job_id,
        state.query.limit,
        state.timeline_offset
      )
      if (
        state.timeline.events.length === 0 ||
        getSelectedTimelineEvent(state) === null
      ) {
        state.selected_timeline_event_key = null
      }
      state.error_message = null
    } catch (error) {
      state.timeline = null
      state.selected_timeline_event_key = null
      state.error_message = getErrorMessage(error)
    } finally {
      renderDashboard(
        app,
        state,
        refreshOverview,
        refreshTimeline,
        refreshControls,
        saveControls
      )
    }
  }

  async function refreshSnapshotInBackground(): Promise<void> {
    if (state.active_view !== 'snapshot') {
      return
    }
    if (shouldPauseBackgroundRefresh()) {
      return
    }
    if (
      state.is_loading ||
      state.controls_is_loading ||
      state.controls_is_saving ||
      state.is_background_refresh_in_flight
    ) {
      return
    }

    state.is_background_refresh_in_flight = true
    try {
      const previousOverview = state.overview
      const previousTimeline = state.timeline
      const nextOverview = await fetchDashboardOverview(state.query)
      let nextTimeline: DashboardJobTimelineResponse | null = null
      if (state.selected_job_id !== null) {
        try {
          nextTimeline = await fetchDashboardTimeline(
            state.selected_job_id,
            state.query.limit,
            state.timeline_offset
          )
        } catch {
          nextTimeline = previousTimeline
        }
      }
      const hasOverviewChanged = !arePayloadsEquivalent(previousOverview, nextOverview)
      const hasTimelineChanged = !arePayloadsEquivalent(previousTimeline, nextTimeline)
      if (!hasOverviewChanged && !hasTimelineChanged) {
        return
      }
      state.overview = nextOverview
      state.timeline = nextTimeline
      if (
        state.timeline === null ||
        state.timeline.events.length === 0 ||
        getSelectedTimelineEvent(state) === null
      ) {
        state.selected_timeline_event_key = null
      }
      applyBackgroundRefreshRowMarkers(
        state,
        previousOverview,
        nextOverview,
        previousTimeline,
        nextTimeline
      )
      state.error_message = null
      renderDashboard(
        app,
        state,
        refreshOverview,
        refreshTimeline,
        refreshControls,
        saveControls
      )
    } catch (error) {
      if (state.overview === null) {
        state.error_message = getErrorMessage(error)
        renderDashboard(
          app,
          state,
          refreshOverview,
          refreshTimeline,
          refreshControls,
          saveControls
        )
      }
    } finally {
      state.is_background_refresh_in_flight = false
    }
  }

  renderDashboard(
    app,
    state,
    refreshOverview,
    refreshTimeline,
    refreshControls,
    saveControls
  )
  try {
    await refreshOverview()
    await refreshControls()
    window.setInterval(() => {
      void refreshSnapshotInBackground()
    }, getDashboardAutoRefreshIntervalMs())
  } catch {
    state.error_message = 'Failed to start dashboard.'
    state.is_loading = false
    renderDashboard(
      app,
      state,
      refreshOverview,
      refreshTimeline,
      refreshControls,
      saveControls
    )
  }
}

const app = typeof document === 'undefined'
  ? null
  : document.querySelector<HTMLDivElement>('#app')

if (app) {
  void startDashboard(app)
}

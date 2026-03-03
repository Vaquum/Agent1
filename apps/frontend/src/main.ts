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
  selected_job_id: string | null
  timeline_offset: number
  selected_timeline_event_key: string | null
  overview: DashboardOverviewResponse | null
  timeline: DashboardJobTimelineResponse | null
  is_loading: boolean
  error_message: string | null
}

const DEFAULT_LIMIT = 20
const DEFAULT_OFFSET = 0
const DEFAULT_API_BASE_URL = 'http://localhost:8000'
const STATUS_OPTIONS = ['', 'ok', 'retry', 'blocked', 'error']

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
    selected_job_id: null,
    timeline_offset: DEFAULT_OFFSET,
    selected_timeline_event_key: null,
    overview: null,
    timeline: null,
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

function createTimelineSectionMarkup(state: DashboardRenderState): string {
  if (state.selected_job_id === null) {
    return `
      <section class='table-section'>
        <h2>Job Timeline</h2>
        <p class='status'>Select a job row to load its transition and event timeline.</p>
      </section>
    `
  }

  if (state.timeline === null) {
    return `
      <section class='table-section'>
        <h2>Job Timeline</h2>
        <p class='status'>Loading timeline for ${escapeHtml(state.selected_job_id)}...</p>
      </section>
    `
  }

  const timelinePageSummary: DashboardPageSummary = {
    limit: state.timeline.transitions_page.limit,
    offset: state.timeline.transitions_page.offset,
    total: Math.max(state.timeline.transitions_page.total, state.timeline.events_page.total)
  }

  const timelineTransitions = createRows(
    state.timeline.transitions.map((transition) => (
      `<tr>
        <td>${escapeHtml(transition.from_state)}</td>
        <td>${escapeHtml(transition.to_state)}</td>
        <td>${escapeHtml(transition.reason)}</td>
        <td>${escapeHtml(formatDateTime(transition.transition_at))}</td>
      </tr>`
    )),
    'No transitions recorded for this job.',
    4
  )
  const timelineEvents = createRows(
    state.timeline.events.map((event) => {
      const eventKey = createTimelineEventKey(event)
      const isSelected = state.selected_timeline_event_key === eventKey
      const selectedClassName = isSelected ? ' class=\'selected-row\'' : ''
      return (
      `<tr>
        <td${selectedClassName}>
          <button
            type='button'
            class='button-secondary inspect-event'
            data-testid='inspect-timeline-event'
            data-event-key='${escapeHtml(eventKey)}'
          >
            ${isSelected ? 'Selected' : 'Inspect'}
          </button>
        </td>
        <td>${escapeHtml(formatDateTime(event.timestamp))}</td>
        <td>${escapeHtml(event.trace_id)}</td>
        <td>${escapeHtml(event.source)}</td>
        <td>${escapeHtml(event.event_type)}</td>
        <td>${escapeHtml(event.status)}</td>
      </tr>`
      )
    }),
    'No events recorded for this job.',
    6
  )
  const selectedEvent = getSelectedTimelineEvent(state)
  let selectedEventMarkup = `
    <section class='event-details-panel'>
      <h3>Selected Timeline Event</h3>
      <p class='status'>Select an event to inspect details and correlated transitions.</p>
    </section>
  `
  if (selectedEvent !== null) {
    const selectedEventReason = getTimelineEventReason(selectedEvent)
    const correlatedTransitions = selectedEventReason === null
      ? []
      : state.timeline.transitions.filter((transition) => transition.reason === selectedEventReason)
    const correlatedTransitionRows = createRows(
      correlatedTransitions.map((transition) => (
        `<tr>
          <td>${escapeHtml(transition.from_state)}</td>
          <td>${escapeHtml(transition.to_state)}</td>
          <td>${escapeHtml(transition.reason)}</td>
          <td>${escapeHtml(formatDateTime(transition.transition_at))}</td>
        </tr>`
      )),
      'No correlated transitions found for selected event.',
      4
    )
    selectedEventMarkup = `
      <section class='event-details-panel'>
        <h3>Selected Timeline Event</h3>
        <p class='status'>
          Trace ${escapeHtml(selectedEvent.trace_id)} at ${escapeHtml(formatDateTime(selectedEvent.timestamp))}
        </p>
        <button
          type='button'
          id='apply-trace-filter'
          class='button-secondary'
          data-testid='apply-trace-filter'
        >
          Filter Overview by Trace
        </button>
        <pre class='event-details-json'>${escapeHtml(formatEventDetails(selectedEvent.details))}</pre>
        <h3>Correlated Transitions</h3>
        <table>
          <thead>
            <tr><th>From</th><th>To</th><th>Reason</th><th>At</th></tr>
          </thead>
          <tbody>${correlatedTransitionRows}</tbody>
        </table>
      </section>
    `
  }

  return `
    <section class='table-section'>
      <h2>Job Timeline: ${escapeHtml(state.timeline.job.job_id)}</h2>
      <p class='status'>${escapeHtml(state.timeline.job.entity_key)}</p>
      ${createPageControlsMarkup('timeline', timelinePageSummary)}
      <table>
        <thead>
          <tr><th>From</th><th>To</th><th>Reason</th><th>At</th></tr>
        </thead>
        <tbody>${timelineTransitions}</tbody>
      </table>
      <table>
        <thead>
          <tr><th>Action</th><th>Timestamp</th><th>Trace</th><th>Source</th><th>Type</th><th>Status</th></tr>
        </thead>
        <tbody>${timelineEvents}</tbody>
      </table>
      ${selectedEventMarkup}
    </section>
  `
}

export function createDashboardMarkup(state: DashboardRenderState): string {
  const overview = state.overview
  const jobs = overview?.jobs ?? []
  const transitions = overview?.transitions ?? []
  const events = overview?.events ?? []
  const anomalies = overview?.anomalies ?? []
  const jobsRows = createRows(
    jobs.map((job) => (
      `<tr>
        <td>
          <button
            type='button'
            class='button-secondary select-job'
            data-testid='select-job-timeline'
            data-job-id='${escapeHtml(job.job_id)}'
          >
            Timeline
          </button>
        </td>
        <td data-testid='job-id-cell'>${escapeHtml(job.job_id)}</td>
        <td>${escapeHtml(job.entity_key)}</td>
        <td>${escapeHtml(job.kind)}</td>
        <td>${escapeHtml(job.state)}</td>
        <td>${escapeHtml(job.environment)}</td>
        <td>${escapeHtml(job.mode)}</td>
        <td>${escapeHtml(String(job.lease_epoch))}</td>
        <td>${escapeHtml(formatDateTime(job.updated_at))}</td>
      </tr>`
    )),
    'No jobs recorded.',
    9
  )
  const transitionRows = createRows(
    transitions.map((transition) => (
      `<tr>
        <td>${escapeHtml(transition.job_id)}</td>
        <td>${escapeHtml(transition.from_state)}</td>
        <td>${escapeHtml(transition.to_state)}</td>
        <td>${escapeHtml(transition.reason)}</td>
        <td>${escapeHtml(formatDateTime(transition.transition_at))}</td>
      </tr>`
    )),
    'No transitions recorded.',
    5
  )
  const eventRows = createRows(
    events.map((event) => (
      `<tr>
        <td>${escapeHtml(formatDateTime(event.timestamp))}</td>
        <td data-testid='overview-trace-cell'>${escapeHtml(event.trace_id)}</td>
        <td>${escapeHtml(event.job_id)}</td>
        <td>${escapeHtml(event.entity_key)}</td>
        <td>${escapeHtml(event.source)}</td>
        <td>${escapeHtml(event.event_type)}</td>
        <td>${escapeHtml(event.status)}</td>
      </tr>`
    )),
    'No events recorded.',
    7
  )
  const anomalyRows = createRows(
    anomalies.map((anomaly) => (
      `<tr>
        <td>${escapeHtml(formatDateTime(anomaly.timestamp))}</td>
        <td>${escapeHtml(anomaly.alert_name)}</td>
        <td>${escapeHtml(anomaly.severity)}</td>
        <td>${escapeHtml(anomaly.trace_id)}</td>
        <td>${escapeHtml(anomaly.job_id)}</td>
        <td>${escapeHtml(anomaly.runbook)}</td>
      </tr>`
    )),
    'No anomalies detected.',
    6
  )
  const statusText = state.error_message ?? (state.is_loading ? 'Loading dashboard snapshot...' : 'Live snapshot')
  const jobsTotal = overview?.jobs_page.total ?? 0
  const transitionsTotal = overview?.transitions_page.total ?? 0
  const eventsTotal = overview?.events_page.total ?? 0
  const anomaliesTotal = overview?.anomalies_page.total ?? 0

  return `
    <main class='layout'>
      <header class='header'>
        <h1>Agent1 Dashboard</h1>
        <p class='status'>${escapeHtml(statusText)}</p>
      </header>
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
        <h2>Recent Transitions</h2>
        ${overview ? `<p class='status'>Filtered count: ${escapeHtml(String(overview.transitions_page.total))}</p>` : ''}
        <table>
          <thead>
            <tr><th>Job</th><th>From</th><th>To</th><th>Reason</th><th>At</th></tr>
          </thead>
          <tbody>${transitionRows}</tbody>
        </table>
      </section>
      <section class='table-section'>
        <h2>Recent Events</h2>
        ${overview ? `<p class='status'>Filtered count: ${escapeHtml(String(overview.events_page.total))}</p>` : ''}
        <table>
          <thead>
            <tr><th>Timestamp</th><th>Trace</th><th>Job</th><th>Entity</th><th>Source</th><th>Type</th><th>Status</th></tr>
          </thead>
          <tbody>${eventRows}</tbody>
        </table>
      </section>
      <section class='table-section'>
        <h2>Recent Anomalies</h2>
        ${overview ? `<p class='status'>Filtered count: ${escapeHtml(String(overview.anomalies_page.total))}</p>` : ''}
        <table>
          <thead>
            <tr><th>Timestamp</th><th>Alert</th><th>Severity</th><th>Trace</th><th>Job</th><th>Runbook</th></tr>
          </thead>
          <tbody>${anomalyRows}</tbody>
        </table>
      </section>
      ${createTimelineSectionMarkup(state)}
    </main>
  `
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

function getErrorMessage(error: unknown): string {
  if (error instanceof Error) {
    return error.message
  }

  return 'Failed to load dashboard snapshot.'
}

function bindDashboardControls(
  app: HTMLDivElement,
  state: DashboardRenderState,
  refreshOverview: () => Promise<void>,
  refreshTimeline: () => Promise<void>
): void {
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
      state.selected_job_id = toOptionalFilterValue(state.query.job_id)
      state.timeline = null
      state.selected_timeline_event_key = null
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

  app.querySelectorAll<HTMLButtonElement>('button.select-job').forEach((button) => {
    button.addEventListener('click', () => {
      const jobId = button.dataset.jobId ?? ''
      if (jobId.trim() === '') {
        return
      }

      state.selected_job_id = jobId
      state.timeline_offset = DEFAULT_OFFSET
      state.timeline = null
      state.selected_timeline_event_key = null
      state.error_message = null
      renderDashboard(app, state, refreshOverview, refreshTimeline)
      void refreshTimeline()
    })
  })

  app.querySelectorAll<HTMLButtonElement>('button.inspect-event').forEach((button) => {
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
      renderDashboard(app, state, refreshOverview, refreshTimeline)
    })
  })

  const applyTraceFilterButton = app.querySelector<HTMLButtonElement>('#apply-trace-filter')
  if (applyTraceFilterButton !== null) {
    applyTraceFilterButton.addEventListener('click', () => {
      const selectedEvent = getSelectedTimelineEvent(state)
      if (selectedEvent === null) {
        return
      }

      state.query.trace_id = selectedEvent.trace_id
      state.query.offset = DEFAULT_OFFSET
      state.timeline_offset = DEFAULT_OFFSET
      state.selected_timeline_event_key = null
      void refreshOverview()
    })
  }

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
}

function renderDashboard(
  app: HTMLDivElement,
  state: DashboardRenderState,
  refreshOverview: () => Promise<void>,
  refreshTimeline: () => Promise<void>
): void {
  app.innerHTML = createDashboardMarkup(state)
  bindDashboardControls(app, state, refreshOverview, refreshTimeline)
}

async function startDashboard(app: HTMLDivElement): Promise<void> {
  const state = createInitialRenderState()

  async function refreshOverview(): Promise<void> {
    state.is_loading = true
    state.error_message = null
    renderDashboard(app, state, refreshOverview, refreshTimeline)
    try {
      state.overview = await fetchDashboardOverview(state.query)
    } catch (error) {
      state.overview = null
      state.timeline = null
      state.error_message = getErrorMessage(error)
    } finally {
      state.is_loading = false
      renderDashboard(app, state, refreshOverview, refreshTimeline)
    }

    if (state.selected_job_id !== null && state.error_message === null) {
      await refreshTimeline()
    }
  }

  async function refreshTimeline(): Promise<void> {
    if (state.selected_job_id === null) {
      state.timeline = null
      renderDashboard(app, state, refreshOverview, refreshTimeline)
      return
    }

    try {
      state.timeline = await fetchDashboardTimeline(
        state.selected_job_id,
        state.query.limit,
        state.timeline_offset
      )
      if (getSelectedTimelineEvent(state) === null) {
        state.selected_timeline_event_key = null
      }
      state.error_message = null
    } catch (error) {
      state.timeline = null
      state.selected_timeline_event_key = null
      state.error_message = getErrorMessage(error)
    } finally {
      renderDashboard(app, state, refreshOverview, refreshTimeline)
    }
  }

  renderDashboard(app, state, refreshOverview, refreshTimeline)
  try {
    await refreshOverview()
  } catch {
    state.error_message = 'Failed to start dashboard.'
    state.is_loading = false
    renderDashboard(app, state, refreshOverview, refreshTimeline)
  }
}

const app = typeof document === 'undefined'
  ? null
  : document.querySelector<HTMLDivElement>('#app')

if (app) {
  void startDashboard(app)
}

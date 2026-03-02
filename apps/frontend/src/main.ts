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

export interface DashboardOverviewResponse {
  jobs: DashboardJobSummary[]
  transitions: DashboardTransitionSummary[]
  events: DashboardEventSummary[]
}

const DASHBOARD_API_LIMIT = 20
const DEFAULT_API_BASE_URL = 'http://localhost:8000'

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

function isDashboardOverviewResponse(payload: unknown): payload is DashboardOverviewResponse {
  if (typeof payload !== 'object' || payload === null) {
    return false
  }

  const record = payload as Record<string, unknown>
  return Array.isArray(record.jobs) && Array.isArray(record.transitions) && Array.isArray(record.events)
}

function createRows(items: string[], emptyMessage: string): string {
  if (items.length === 0) {
    return `<tr><td colspan='8' class='empty-row'>${escapeHtml(emptyMessage)}</td></tr>`
  }

  return items.join('')
}

export function createDashboardMarkup(
  overview: DashboardOverviewResponse | null,
  errorMessage: string | null = null
): string {
  const jobs = overview?.jobs ?? []
  const transitions = overview?.transitions ?? []
  const events = overview?.events ?? []
  const jobsRows = createRows(
    jobs.map((job) => (
      `<tr>
        <td>${escapeHtml(job.job_id)}</td>
        <td>${escapeHtml(job.entity_key)}</td>
        <td>${escapeHtml(job.kind)}</td>
        <td>${escapeHtml(job.state)}</td>
        <td>${escapeHtml(job.environment)}</td>
        <td>${escapeHtml(job.mode)}</td>
        <td>${escapeHtml(String(job.lease_epoch))}</td>
        <td>${escapeHtml(formatDateTime(job.updated_at))}</td>
      </tr>`
    )),
    'No jobs recorded.'
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
    'No transitions recorded.'
  )
  const eventRows = createRows(
    events.map((event) => (
      `<tr>
        <td>${escapeHtml(formatDateTime(event.timestamp))}</td>
        <td>${escapeHtml(event.trace_id)}</td>
        <td>${escapeHtml(event.job_id)}</td>
        <td>${escapeHtml(event.entity_key)}</td>
        <td>${escapeHtml(event.source)}</td>
        <td>${escapeHtml(event.event_type)}</td>
        <td>${escapeHtml(event.status)}</td>
      </tr>`
    )),
    'No events recorded.'
  )
  const statusText = errorMessage ?? (overview === null ? 'Loading dashboard snapshot...' : 'Live snapshot')

  return `
    <main class='layout'>
      <header class='header'>
        <h1>Agent1 Dashboard</h1>
        <p class='status'>${escapeHtml(statusText)}</p>
      </header>
      <section class='metrics'>
        <article class='metric-card'><h2>Jobs</h2><p>${jobs.length}</p></article>
        <article class='metric-card'><h2>Transitions</h2><p>${transitions.length}</p></article>
        <article class='metric-card'><h2>Events</h2><p>${events.length}</p></article>
      </section>
      <section class='table-section'>
        <h2>Recent Jobs</h2>
        <table>
          <thead>
            <tr><th>Job</th><th>Entity</th><th>Kind</th><th>State</th><th>Env</th><th>Mode</th><th>Lease</th><th>Updated</th></tr>
          </thead>
          <tbody>${jobsRows}</tbody>
        </table>
      </section>
      <section class='table-section'>
        <h2>Recent Transitions</h2>
        <table>
          <thead>
            <tr><th>Job</th><th>From</th><th>To</th><th>Reason</th><th>At</th></tr>
          </thead>
          <tbody>${transitionRows}</tbody>
        </table>
      </section>
      <section class='table-section'>
        <h2>Recent Events</h2>
        <table>
          <thead>
            <tr><th>Timestamp</th><th>Trace</th><th>Job</th><th>Entity</th><th>Source</th><th>Type</th><th>Status</th></tr>
          </thead>
          <tbody>${eventRows}</tbody>
        </table>
      </section>
    </main>
  `
}

async function fetchDashboardOverview(): Promise<DashboardOverviewResponse> {
  const configuredApiBaseUrl = (import.meta.env.VITE_AGENT1_API_BASE_URL as string | undefined) ?? ''
  const apiBaseUrl = configuredApiBaseUrl.trim() === ''
    ? DEFAULT_API_BASE_URL
    : configuredApiBaseUrl.trim()
  const requestUrl = `${apiBaseUrl}/dashboard/overview?limit=${DASHBOARD_API_LIMIT}`
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

function getErrorMessage(error: unknown): string {
  if (error instanceof Error) {
    return error.message
  }

  return 'Failed to load dashboard snapshot.'
}

async function renderDashboard(app: HTMLDivElement): Promise<void> {
  app.innerHTML = createDashboardMarkup(null)
  try {
    const overview = await fetchDashboardOverview()
    app.innerHTML = createDashboardMarkup(overview)
  } catch (error) {
    app.innerHTML = createDashboardMarkup(null, getErrorMessage(error))
  }
}

const app = typeof document === 'undefined'
  ? null
  : document.querySelector<HTMLDivElement>('#app')

if (app) {
  void renderDashboard(app)
}

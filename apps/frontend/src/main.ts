import './styles.css'

export const DASHBOARD_SCAFFOLD_HTML = `
  <main class='layout'>
    <h1>Agent1</h1>
    <p>Operations dashboard scaffold is ready.</p>
  </main>
`

const app = typeof document === 'undefined'
  ? null
  : document.querySelector<HTMLDivElement>('#app')

if (app) {
  app.innerHTML = DASHBOARD_SCAFFOLD_HTML
}

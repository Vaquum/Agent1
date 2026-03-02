import './styles.css'

const app = document.querySelector<HTMLDivElement>('#app')

if (app) {
  app.innerHTML = `
    <main class="layout">
      <h1>Agent1</h1>
      <p>Operations dashboard scaffold is ready.</p>
    </main>
  `
}

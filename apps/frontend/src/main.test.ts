import { describe, expect, it } from 'vitest'

import { DASHBOARD_SCAFFOLD_HTML } from './main'

describe('dashboard scaffold html', () => {
  it('contains the expected title and body text', () => {
    expect(DASHBOARD_SCAFFOLD_HTML).toContain('<h1>Agent1</h1>')
    expect(DASHBOARD_SCAFFOLD_HTML).toContain('Operations dashboard scaffold is ready.')
  })
})

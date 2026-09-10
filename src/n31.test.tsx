/// <reference types="node" />
// @vitest-environment jsdom
import { describe, expect, it, afterEach } from 'vitest'
import { readFileSync, readdirSync } from 'node:fs'
import ts from 'typescript'
import { createElement, act } from 'react'
import { createRoot } from 'react-dom/client'
import { linkifyText, LinkText } from './ui'
import { setActiveLocale } from './i18n'
import { StoreProvider } from './store'
import { seed } from './domain/engine'
import { NotificationsView } from './views/Notifications'

afterEach(() => { setActiveLocale('en'); localStorage.clear() })
describe('N3.1 production text classification', () => {
  const files = ['src/App.tsx','src/ui.tsx',
    ...readdirSync('src/views').filter(f => f.endsWith('.tsx') && f !== 'TestLab.tsx').map(f => `src/views/${f}`),
    ...readdirSync('src/components').filter(f => f.endsWith('.tsx') && f !== 'DevSwitch.tsx').map(f => `src/components/${f}`)]
  it('has no raw system prose in JSX text or user-facing literal attributes', () => {
    const found: string[] = []
    for (const file of files) {
      const source = ts.createSourceFile(file, readFileSync(file,'utf8'), ts.ScriptTarget.Latest, true, ts.ScriptKind.TSX)
      const visit = (n: ts.Node) => {
        if (ts.isJsxText(n) && /[a-z]{2}/i.test(n.text.trim())) {
          // Company name: authored seed content, not a system label.
          if (!(file.endsWith('/Login.tsx') && n.text.trim() === 'Aster Dynamics')) found.push(`${file}: ${n.text.trim()}`)
        }
        if (ts.isJsxAttribute(n) && ['title','placeholder','aria-label','alt'].includes(n.name.getText(source)) && n.initializer && ts.isStringLiteral(n.initializer) && /[a-z]{2}/i.test(n.initializer.text)) found.push(`${file}: ${n.getText(source)}`)
        ts.forEachChild(n, visit)
      }
      visit(source)
    }
    expect(found).toEqual([])
  })
})
describe('N3.1 bidi link regression', () => {
  for (const locale of ['fa','ar','he']) {
    it(`${locale} preserves bare domains and rejects file.py`, () => {
      setActiveLocale(locale)
      const tokens = linkifyText('متن example.com file.py')
      expect(JSON.stringify(tokens)).toContain('https://example.com')
      expect(JSON.stringify(tokens)).not.toContain('https://file.py')
    })
  }
  it('Persian user text remains unchanged in English and uses auto direction', async () => {
    const host = document.createElement('div')
    const root = createRoot(host)
    const text = 'عنوان فارسی example.com file.py'
    await act(async () => root.render(createElement(LinkText, { text })))
    expect(host.textContent).toBe(text)
    expect(host.querySelector('[dir="auto"]')).not.toBeNull()
    expect(host.querySelector('a')?.getAttribute('href')).toBe('https://example.com')
    await act(async () => root.unmount())
  })
})
it('localizes typed notice categories while leaving saved prose unchanged', async () => {
  setActiveLocale('fa')
  const state = seed()
  const original = state.notices.find(n => n.category === 'Assignments' && n.userId === 'u-marcus')!
  localStorage.setItem('cve-demo-state-v1', JSON.stringify({ v:2, state }))
  const host = document.createElement('div')
  const root = createRoot(host)
  await act(async () => root.render(createElement(StoreProvider, null,
    createElement(NotificationsView, { onOpenTask:() => {}, onOpenRedemption:() => {} }))))
  expect(host.textContent).toContain(original.text)
  expect(host.textContent).toContain('تخصیص‌ها')
  expect(host.querySelector('.meta')?.textContent).not.toContain('Assignments')
  const saved = JSON.parse(localStorage.getItem('cve-demo-state-v1')!)
  expect(saved.state.notices.find((n: {id:string}) => n.id === original.id)).toEqual(original)
  await act(async () => root.unmount())
})

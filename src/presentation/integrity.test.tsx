// @vitest-environment jsdom
import { afterEach, beforeEach, expect, it, vi } from 'vitest'
import { act, type ReactNode } from 'react'
import { createRoot, type Root } from 'react-dom/client'
import { renderToStaticMarkup } from 'react-dom/server'
import { ClampedText } from './UserText'
import { newestFirst } from './historyOrder'
import { SystemToast } from './SystemToast'
import { newAudibleNotices, NotificationAudio } from './NotificationAudio'
import { seed, type Action } from '../domain/engine'
import { StoreProvider, useStore } from '../store'
import { ReturnModal } from '../components/TaskModals'
import { Debt } from './Debt'
import { ApiError, api, bindSessionToken, setToken } from '../api'
import { setActiveLocale, translate } from '../i18n'
import { errorText } from './errorText'

let host: HTMLDivElement, root: Root | null = null
beforeEach(() => { host = document.createElement('div'); document.body.appendChild(host); setActiveLocale('en'); (globalThis as Record<string, unknown>).IS_REACT_ACT_ENVIRONMENT = true })
afterEach(async () => { if (root) await act(async () => root?.unmount()); root = null; host.remove(); vi.useRealTimers(); vi.unstubAllGlobals(); setActiveLocale('en'); bindSessionToken(null); localStorage.clear() })
async function mount(node: ReactNode) { root = createRoot(host); await act(async () => root!.render(node)) }

it.each(['en','fa','he'])('preserves authored lines, lists, indentation and safe links in %s', locale => {
  setActiveLocale(locale)
  const text = 'First\nSecond\n\n1. item\n2. item\n- bullet\n  - child\nhttps://example.com\n<script>alert(1)</script>'
  host.innerHTML = renderToStaticMarkup(<ClampedText text={text} />)
  expect(host.querySelector('.clampbox')?.textContent).toBe(text)
  expect((host.querySelector('.clampbox') as HTMLElement).style.whiteSpace).toBe('pre-wrap')
  expect(host.querySelector('a')?.href).toBe('https://example.com/')
  expect(host.querySelector('script')).toBeNull()
})
it('history sorts newest first with deterministic sequence ties without mutating source', () => {
  const rows = [{id:'a9',at:4},{id:'a10',at:4},{id:'a3',at:3}]
  expect([...rows].sort(newestFirst).map(r => r.id)).toEqual(['a10','a9','a3'])
  expect(rows[0].id).toBe('a9')
})
it('toast lasts ten seconds and manual Close works', async () => {
  vi.useFakeTimers(); const close = vi.fn()
  await mount(<SystemToast message="Readable error" onClose={close} />)
  await act(async () => vi.advanceTimersByTime(9999)); expect(close).not.toHaveBeenCalled()
  await act(async () => vi.advanceTimersByTime(1)); expect(close).toHaveBeenCalledTimes(1)
  await act(async () => host.querySelector('button')!.click()); expect(close).toHaveBeenCalledTimes(2)
  expect(host.querySelector('button')?.getAttribute('aria-label')).toBe('Close')
})
it('toast pauses on keyboard focus', async () => {
  vi.useFakeTimers(); const close = vi.fn()
  await mount(<SystemToast message="Readable error" onClose={close} />)
  await act(async () => vi.advanceTimersByTime(4000))
  await act(async () => host.querySelector('button')!.focus())
  await act(async () => vi.advanceTimersByTime(20000)); expect(close).not.toHaveBeenCalled()
  await act(async () => host.querySelector('button')!.blur())
  await act(async () => vi.advanceTimersByTime(6000)); expect(close).toHaveBeenCalledTimes(1)
})
it('audio candidates exclude historical/read/archived/muted/low priority notices', () => {
  const n = {...seed().notices[0], id:'new', userId:'u-priya', level:'ACTION_REQUIRED' as const, read:false, archived:false}
  expect(newAudibleNotices([n], new Set(), 'u-priya', [])).toBe(true)
  expect(newAudibleNotices([n], new Set(['new']), 'u-priya', [])).toBe(false)
  for (const notice of [{...n,read:true},{...n,archived:true},{...n,level:'INFORMATIONAL' as const}]) expect(newAudibleNotices([notice], new Set(), 'u-priya', [])).toBe(false)
  expect(newAudibleNotices([n], new Set(), 'u-priya', ['ACTION_REQUIRED'])).toBe(false)
})
it.each(['en','fa','he','ar','hi','zh-CN','ja','ko','ru','tr'])('known refusals are localized in %s without backend English', locale => {
  setActiveLocale(locale)
  expect(errorText(new ApiError(403,'FORBIDDEN','Sensitive raw backend message'))).toBe(translate(locale,'integrity.error.FORBIDDEN'))
  expect(errorText(new ApiError(409,'REVIEW_AUTHORITY_REQUIRED','Sensitive raw backend message'))).not.toMatch(/Sensitive|integrity\./)
})
it('another tab token write cannot silently change this tab request identity', async () => {
  const fetch = vi.fn().mockResolvedValue({ok:true,status:200,json:async()=>({})}); vi.stubGlobal('fetch',fetch)
  setToken('ray-token'); bindSessionToken('ray-token')
  localStorage.setItem('cve-token','marcus-token')
  await api.post('/notices/ray-notice/read')
  expect(fetch.mock.calls[0][1].headers.Authorization).toBe('Bearer ray-token')
  bindSessionToken('marcus-token'); await api.bootstrap()
  expect(fetch.mock.calls[1][1].headers.Authorization).toBe('Bearer marcus-token')
})

it('unlocked audio sounds once per new batch, respects sound-off and never replays bootstrap', async () => {
  vi.useFakeTimers()
  const oscillator = vi.fn(() => ({ type:'', frequency:{setValueAtTime:vi.fn(),exponentialRampToValueAtTime:vi.fn()}, connect:vi.fn(),disconnect:vi.fn(),start:vi.fn(),stop:vi.fn(),onended:null }))
  vi.stubGlobal('AudioContext', class {
    state='running'; currentTime=0; destination={}
    resume=async()=>{}; close=async()=>{}; createOscillator=oscillator
    createGain=()=>({gain:{setValueAtTime:vi.fn(),exponentialRampToValueAtTime:vi.fn()},connect:vi.fn(),disconnect:vi.fn()})
  })
  localStorage.setItem('cve-demo-me-v1','u-priya')
  let dispatch: (a: Action) => void = () => {}
  function Harness() { dispatch = useStore().dispatch; return <NotificationAudio /> }
  await mount(<StoreProvider><Harness /></StoreProvider>)
  expect(oscillator).not.toHaveBeenCalled()
  await act(async () => window.dispatchEvent(new Event('pointerdown')))
  const adjust = () => dispatch({type:'ADMIN_ADJUST',by:'u-dana',userId:'u-priya',amount:1,reason:'Credit'})
  await act(async () => { adjust(); adjust() }); expect(oscillator).toHaveBeenCalledTimes(1)
  await act(async () => vi.advanceTimersByTime(1100))
  await act(async () => host.querySelector('button')!.click())
  await act(async () => adjust()); expect(oscillator).toHaveBeenCalledTimes(1)
  await act(async () => root!.render(<StoreProvider><Harness key="reload" /></StoreProvider>))
  expect(oscillator).toHaveBeenCalledTimes(1)
})

it('wallet debt and Return confirmation show nonnegative balance plus the full fractional penalty', async () => {
  const s = seed(); s.ledger = [{...s.ledger[0], userId:'u-priya', amount:-8}]
  const task = {...s.tasks[0], ownerId:'u-priya', priority:'IMPORTANT' as const}
  localStorage.setItem('cve-demo-me-v1','u-priya')
  localStorage.setItem('cve-demo-state-v1',JSON.stringify({v:2,state:s}))
  await mount(<StoreProvider><Debt userId="u-priya" /><ReturnModal open onClose={()=>{}} task={task} /></StoreProvider>)
  expect(host.querySelector('[data-testid="coin-debt"]')?.textContent).toContain('8')
  const modal = document.querySelector('.modal')!
  expect(modal.textContent).toContain('7.5')
  expect(modal.textContent).toContain('15.5')
  expect(modal.textContent).toContain('Spendable balance after return')
})

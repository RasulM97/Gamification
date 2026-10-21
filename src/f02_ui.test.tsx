// @vitest-environment jsdom
import { act } from 'react'
import { createRoot, type Root } from 'react-dom/client'
import { afterEach, expect, it, vi } from 'vitest'
import { api, ApiError, setToken } from './api'
import { seed } from './domain/engine'
import { StoreProvider, useStore } from './store'
import { SubmitModal } from './components/TaskModals'
import { SystemToast } from './presentation/SystemToast'

vi.mock('./runtime', () => ({ DATA_MODE: 'server', IS_DEMO: false, WORKSPACE_TOOLS: false, DEV_TOOLS: false }))
let root: Root | undefined, host: HTMLDivElement | undefined
afterEach(async () => {
  if (root) await act(async () => root?.unmount())
  root = undefined; host?.remove(); vi.restoreAllMocks(); vi.useRealTimers(); sessionStorage.clear()
})

it('keeps the draft open through pending and unknown, blocks double clicks, closes only after confirmation', async () => {
  ;(globalThis as Record<string, unknown>).IS_REACT_ACT_ENVIRONMENT = true
  setToken('f02-ui-session')
  const state = seed(), task = state.tasks.find(t => t.id === 't-pricing')!
  vi.spyOn(api, 'me').mockResolvedValue({ id: 'u-priya', name: 'Priya', role: 'EMPLOYEE', position: '', email: '', companyId: 'co-aster' })
  vi.spyOn(api, 'bootstrap').mockResolvedValue(state)
  let reject!: (reason: unknown) => void
  const send = vi.spyOn(api, 'postForm').mockImplementationOnce(() => new Promise((_resolve, fail) => { reject = fail }))
  const close = vi.fn()
  function Harness() {
    const store = useStore()
    if (store.auth !== 'ready') return null
    return <><SubmitModal open onClose={close} task={task} /><SystemToast message={store.persistError} onClose={store.dismissError} persistent /></>
  }
  host = document.createElement('div'); document.body.appendChild(host); root = createRoot(host)
  await act(async () => root!.render(<StoreProvider><Harness /></StoreProvider>))
  const textarea = document.querySelector('textarea')!
  await act(async () => {
    Object.getOwnPropertyDescriptor(HTMLTextAreaElement.prototype, 'value')!.set!.call(textarea, 'Do not lose this draft')
    textarea.dispatchEvent(new Event('input', { bubbles: true }))
  })
  const submit = document.querySelector('.modal .btn.primary') as HTMLButtonElement
  await act(async () => { submit.click(); submit.click() })
  expect(send).toHaveBeenCalledTimes(1)
  expect(close).not.toHaveBeenCalled()
  expect(document.querySelector('[role="alert"]')?.textContent).toContain('Saving')
  await act(async () => reject(new ApiError(503, 'OUTCOME_UNKNOWN', 'unknown')))
  expect(close).not.toHaveBeenCalled()
  expect(textarea.value).toBe('Do not lose this draft')
  expect(document.querySelector('[role="alert"]')?.textContent).toContain('Outcome unknown')
  send.mockResolvedValueOnce(state)
  await act(async () => submit.click())
  expect(close).toHaveBeenCalledTimes(1)
})

it('does not silently expire persistent server outcome feedback', async () => {
  ;(globalThis as Record<string, unknown>).IS_REACT_ACT_ENVIRONMENT = true
  vi.useFakeTimers()
  const close = vi.fn()
  host = document.createElement('div'); document.body.appendChild(host); root = createRoot(host)
  await act(async () => root!.render(<SystemToast message="Outcome unknown" persistent onClose={close} />))
  await act(async () => vi.advanceTimersByTime(60000))
  expect(close).not.toHaveBeenCalled()
  await act(async () => host!.querySelector('button')!.click())
  expect(close).toHaveBeenCalledOnce()
})

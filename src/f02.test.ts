// @vitest-environment jsdom
import { webcrypto } from 'node:crypto'
import { afterEach, beforeEach, expect, it, vi } from 'vitest'
import { api, bindSessionToken, ApiError } from './api'

beforeEach(() => { sessionStorage.clear(); vi.stubGlobal('crypto', webcrypto); bindSessionToken('f02-test-session') })
afterEach(() => { vi.unstubAllGlobals(); vi.restoreAllMocks(); vi.useRealTimers(); bindSessionToken(null) })
const body = { userId: 'u-priya', amount: 7, reason: 'Credit' }
const ok = () => new Response(JSON.stringify({ saved: true }), { status: 200 })

it('retains retry identity after lost response, including module reload; new success gets a new identity', async () => {
  const fetch = vi.fn().mockRejectedValueOnce(new TypeError('lost response')).mockResolvedValueOnce(ok()).mockResolvedValueOnce(ok())
  vi.stubGlobal('fetch', fetch)
  await expect(api.post('/admin/adjust', body)).rejects.toMatchObject({ code: 'OUTCOME_UNKNOWN' })
  const first = fetch.mock.calls[0][1].headers['Idempotency-Key']
  vi.resetModules()
  const reloaded = await import('./api')
  reloaded.bindSessionToken('f02-test-session')
  await reloaded.api.post('/admin/adjust', body)
  expect(fetch.mock.calls[1][1].headers['Idempotency-Key']).toBe(first)
  await reloaded.api.post('/admin/adjust', body)
  expect(fetch.mock.calls[2][1].headers['Idempotency-Key']).not.toBe(first)
})

it('blocks changed economic details while the original outcome is unresolved', async () => {
  const fetch = vi.fn().mockRejectedValue(new TypeError('lost'))
  vi.stubGlobal('fetch', fetch)
  await expect(api.post('/admin/adjust', body)).rejects.toBeInstanceOf(ApiError)
  await expect(api.post('/admin/adjust', { ...body, amount: 8 })).rejects.toMatchObject({ code: 'COMMAND_KEY_CONFLICT' })
  expect(fetch).toHaveBeenCalledTimes(1)
})

it.each(['OUTCOME_UNKNOWN', 'COMMAND_COMMITTED'])('preserves identity on %s and never retries automatically', async code => {
  const fetch = vi.fn().mockResolvedValueOnce(new Response(JSON.stringify({ detail: { code } }), { status: 503 })).mockResolvedValueOnce(ok())
  vi.stubGlobal('fetch', fetch)
  await expect(api.post('/admin/adjust', body)).rejects.toMatchObject({ code })
  expect(fetch).toHaveBeenCalledTimes(1)
  await api.post('/admin/adjust', body)
  expect(fetch.mock.calls[0][1].headers['Idempotency-Key']).toBe(fetch.mock.calls[1][1].headers['Idempotency-Key'])
})

it('fails before sending when durable retry metadata cannot be saved', async () => {
  vi.spyOn(Storage.prototype, 'setItem').mockImplementation(() => { throw new Error('quota') })
  const fetch = vi.fn(); vi.stubGlobal('fetch', fetch)
  await expect(api.post('/admin/adjust', body)).rejects.toMatchObject({ code: 'RETRY_STORAGE_UNAVAILABLE' })
  expect(fetch).not.toHaveBeenCalled()
})

it('does not call a malformed success body a confirmed rollback', async () => {
  const fetch = vi.fn().mockResolvedValueOnce(new Response('truncated', { status: 200 })).mockResolvedValueOnce(ok())
  vi.stubGlobal('fetch', fetch)
  await expect(api.post('/admin/adjust', body)).rejects.toMatchObject({ code: 'OUTCOME_UNKNOWN' })
  await api.post('/admin/adjust', body)
  expect(fetch.mock.calls[0][1].headers['Idempotency-Key']).toBe(fetch.mock.calls[1][1].headers['Idempotency-Key'])
})

it('keeps the same identity across renewed sessions for the same actor', async () => {
  const token = (sid: string) => 'test.' + btoa(JSON.stringify({ sub: 'u-priya', cid: 'co-aster', sid })) + '.signature'
  const fetch = vi.fn().mockRejectedValueOnce(new TypeError('lost')).mockResolvedValueOnce(ok())
  vi.stubGlobal('fetch', fetch)
  bindSessionToken(token('old-session'))
  await expect(api.post('/redemptions', { rewardId: 'rw-coffee' })).rejects.toMatchObject({ code: 'OUTCOME_UNKNOWN' })
  bindSessionToken(token('new-session'))
  await api.post('/redemptions', { rewardId: 'rw-coffee' })
  expect(fetch.mock.calls[0][1].headers['Idempotency-Key']).toBe(fetch.mock.calls[1][1].headers['Idempotency-Key'])
})

it('does not discard an uncertain identity on auth refusal, but accepts a locked NOT_COMMITTED refusal', async () => {
  const fetch = vi.fn().mockRejectedValueOnce(new TypeError('lost'))
    .mockResolvedValueOnce(new Response('{}', { status: 401 }))
    .mockResolvedValueOnce(new Response(JSON.stringify({ code: 'FORBIDDEN', commandOutcome: 'NOT_COMMITTED' }), { status: 403 }))
    .mockResolvedValueOnce(ok())
  vi.stubGlobal('fetch', fetch)
  await expect(api.post('/admin/adjust', body)).rejects.toMatchObject({ code: 'OUTCOME_UNKNOWN' })
  await expect(api.post('/admin/adjust', body)).rejects.toMatchObject({ status: 401 })
  await expect(api.post('/admin/adjust', body)).rejects.toMatchObject({ code: 'FORBIDDEN' })
  const keys = fetch.mock.calls.map(call => call[1].headers['Idempotency-Key'])
  expect(new Set(keys).size).toBe(1)
  await api.post('/admin/adjust', { ...body, amount: 8 })
  expect(fetch.mock.calls[3][1].headers['Idempotency-Key']).not.toBe(keys[0])
})

it('bounds a stalled response and preserves its identity for an explicit retry', async () => {
  vi.useFakeTimers()
  const fetch = vi.fn((_url, options) => new Promise<Response>((_resolve, reject) => {
    options.signal.addEventListener('abort', () => reject(new DOMException('Timed out', 'AbortError')))
  }))
  vi.stubGlobal('fetch', fetch)
  const outcome = expect(api.post('/admin/adjust', body)).rejects.toMatchObject({ code: 'OUTCOME_UNKNOWN' })
  await vi.waitFor(() => expect(fetch).toHaveBeenCalledOnce())
  await vi.advanceTimersByTimeAsync(30001)
  await outcome
  vi.useRealTimers()
  fetch.mockResolvedValueOnce(ok())
  await api.post('/admin/adjust', body)
  expect(fetch.mock.calls[0][1].headers['Idempotency-Key']).toBe(fetch.mock.calls[1][1].headers['Idempotency-Key'])
})

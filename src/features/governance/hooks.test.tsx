// @vitest-environment jsdom
import { act } from 'react'
import { createRoot } from 'react-dom/client'
import { expect, it } from 'vitest'
import { useGovData } from './hooks'

it('ignores an old persona/request finishing after a newer authoritative read', async () => {
  Object.assign(globalThis, { IS_REACT_ACT_ENVIRONMENT: true })
  const host = document.createElement('div'), root = createRoot(host)
  let old!: (s: string) => void, current!: (s: string) => void
  const first = new Promise<string>(r => { old = r }), second = new Promise<string>(r => { current = r })
  function Probe({ persona }: { persona: number }) {
    const result = useGovData(() => persona === 1 ? first : second, [persona])
    return <span>{result.loading ? 'loading' : result.data}</span>
  }
  await act(async () => { root.render(<Probe persona={1} />) })
  await act(async () => { root.render(<Probe persona={2} />) })
  await act(async () => { current('current') })
  expect(host.textContent).toBe('current')
  await act(async () => { old('stale') })
  expect(host.textContent).toBe('current')
  await act(async () => { root.unmount() })
})

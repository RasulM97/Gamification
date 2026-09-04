// @vitest-environment jsdom
/* M1-D D6 (demo half) — demo attachments must NEVER imply real file bytes:
   the chip is marked "demo" and the opened preview states upfront that the
   file content is unavailable. Runs against the real runtime (demo default). */
import { afterEach, describe, expect, it, vi } from 'vitest'
import { createElement } from 'react'
import { createRoot } from 'react-dom/client'
import { AttachmentChips, openAttachment } from './ui'
import type { Attachment } from './domain/engine'

const FILE: Attachment = { name: 'field-report.pdf', size: 2 * 1048576, type: 'application/pdf' }

describe('demo attachments stay honest', () => {
  afterEach(() => vi.restoreAllMocks())

  it('chips carry an explicit demo marker and unavailable-content tooltip', async () => {
    const host = document.createElement('div')
    document.body.appendChild(host)
    createRoot(host).render(createElement(AttachmentChips, { files: [FILE] }))
    await new Promise(r => setTimeout(r, 10))
    const btn = host.querySelector('button')!
    expect(btn.textContent).toContain('field-report.pdf')
    expect(btn.textContent).toContain('demo')
    expect(btn.title).toContain('file content unavailable')
    host.remove()
  })

  it('opening a demo attachment shows "file content unavailable" first', async () => {
    let blob: Blob | null = null
    const opened: string[] = []
    URL.createObjectURL = vi.fn((b: Blob) => { blob = b; return 'blob:demo' }) as unknown as typeof URL.createObjectURL
    URL.revokeObjectURL = vi.fn() as unknown as typeof URL.revokeObjectURL
    window.open = vi.fn((url?: string) => { opened.push(url!); return null }) as unknown as typeof window.open
    openAttachment(FILE)
    expect(opened).toEqual(['blob:demo'])
    const text = await (blob as unknown as Blob).text()
    expect(text.split('\n')[0]).toBe('Demo attachment — file content unavailable')
    expect(text).toContain('Name: field-report.pdf')
  })
})

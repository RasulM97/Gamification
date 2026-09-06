// @vitest-environment jsdom
/* M1-D D6 (server half) — server attachments are REAL stored files: the chip
   presents an open affordance and clicking downloads the authenticated bytes
   through /api/files/{id}. Runtime is mocked to server mode for this file. */
import { afterEach, describe, expect, it, vi } from 'vitest'
import { createElement } from 'react'
import { createRoot } from 'react-dom/client'

vi.mock('./runtime', () => ({ IS_DEMO: false, DATA_MODE: 'server', DEV_TOOLS: false }))
const openStoredFile = vi.fn((_id: string, _name: string) => Promise.resolve())
vi.mock('./api', () => ({ openStoredFile: (...args: unknown[]) => openStoredFile(...args as [string, string]) }))

import { AttachmentChips, openAttachment } from './ui'
import type { Attachment } from './domain/engine'

const STORED: Attachment = { id: 'att-1', name: 'evidence.xlsx', size: 1048576, type: 'application/vnd.ms-excel' }
const QUEUED: Attachment = { name: 'not-yet-stored.txt', size: 10, type: 'text/plain' }

describe('server attachments are interactive real files', () => {
  afterEach(() => { openStoredFile.mockClear(); vi.restoreAllMocks() })

  it('chips show an open affordance and a real-file tooltip (no demo marker)', async () => {
    const host = document.createElement('div')
    document.body.appendChild(host)
    createRoot(host).render(createElement(AttachmentChips, { files: [STORED] }))
    await new Promise(r => setTimeout(r, 10))
    const btn = host.querySelector('button')!
    expect(btn.textContent).toContain('evidence.xlsx')
    expect(btn.textContent).toContain('↗')
    expect(btn.textContent).not.toContain('demo')
    expect(btn.title).toContain('opens in a new tab')
    host.remove()
  })

  it('clicking a stored file downloads the real bytes via openStoredFile(id)', () => {
    openAttachment(STORED)
    expect(openStoredFile).toHaveBeenCalledWith('att-1', 'evidence.xlsx')
  })

  it('a form-queued attachment (no stored id) is never opened as if real', () => {
    openAttachment(QUEUED)
    expect(openStoredFile).not.toHaveBeenCalled()
  })
})

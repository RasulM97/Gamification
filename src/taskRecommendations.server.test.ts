import { expect, it, vi } from 'vitest'
const post = vi.hoisted(() => vi.fn().mockResolvedValue({}))
vi.mock('./api', () => ({ api: { post } }))
import { send } from './storeRequests'
import { supportsCommandIdentity } from './commandIdentity'

it('sends only exact submission identity and note through the existing durable retry boundary', async () => {
  await send({ type: 'RECOMMEND_APPROVAL', taskId: 't-1', managerId: 'manager', cycle: 3,
    submissionId: 'sub-7', note: 'Checked evidence' })
  expect(post).toHaveBeenCalledWith('/tasks/t-1/recommendation', {
    cycle: 3, submissionId: 'sub-7', note: 'Checked evidence' })
  expect(supportsCommandIdentity('/tasks/t-1/recommendation')).toBe(true)
})

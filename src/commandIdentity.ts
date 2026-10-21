/* Retry metadata only: no token, form text, files or domain state is persisted. */
const prefix = 'cve-command:'
export class CommandIdentityConflict extends Error {}
const digest = async (data: BufferSource) => Array.from(new Uint8Array(
  await crypto.subtle.digest('SHA-256', data))).map(x => x.toString(16).padStart(2, '0')).join('')

function actorNamespace(token: string): unknown {
  // Group retry metadata across renewed sessions only. This is NOT an
  // authorization check: the server verifies JWT/session and scopes receipts.
  try {
    const payload = JSON.parse(atob(token.split('.')[1].replace(/-/g, '+').replace(/_/g, '/')))
    if (typeof payload.sub === 'string' && typeof payload.cid === 'string') return [payload.cid, payload.sub]
  } catch { /* opaque token: keep the token-specific namespace */ }
  return token
}

export function supportsCommandIdentity(path: string): boolean {
  return /^\/(tasks(?:\/|$)|redemptions(?:\/|$)|rewards(?:\/|$)|reward-categories(?:\/|$)|admin\/adjust$)/.test(path)
}

export async function commandIdentity(token: string, method: string, path: string, json?: unknown, form?: FormData) {
  const fields: unknown[] = []
  if (form) {
    for (const [name, value] of form.entries()) {
      fields.push([name, typeof value === 'string' ? value
        : [value.name, value.type, await digest(await value.arrayBuffer())]])
    }
  }
  const encode = (value: unknown) => new TextEncoder().encode(JSON.stringify(value))
  const fingerprint = await digest(encode([json ?? null, fields]))
  const slot = prefix + await digest(encode([actorNamespace(token), method, path]))
  const raw = sessionStorage.getItem(slot)
  const prior = raw ? JSON.parse(raw) as { key: string; fingerprint: string } : null
  if (prior && (!/^[a-zA-Z0-9_-]{16,80}$/.test(prior.key) || !/^[a-f0-9]{64}$/.test(prior.fingerprint))) throw new Error('Invalid retry metadata')
  if (prior && prior.fingerprint !== fingerprint) throw new CommandIdentityConflict()
  const key = prior?.key ?? crypto.randomUUID()
  sessionStorage.setItem(slot, JSON.stringify({ key, fingerprint })) // Fail closed before sending if persistence is unavailable.
  return { key, retry: prior !== null, complete: () => sessionStorage.removeItem(slot) }
}

/** Stable newest-first display only; numeric demo IDs preserve sequence ties. */
export function newestFirst(a: { at: number; id: string }, b: { at: number; id: string }) {
  return b.at - a.at || b.id.localeCompare(a.id, 'en', { numeric: true })
}

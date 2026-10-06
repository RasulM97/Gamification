/* WS2-A: shared business-language rendering for provenance projections.
 * Event types are translated only when a phrase exists — unknown codes are
 * never shown to employees; manager/admin surfaces may show the code muted
 * as secondary information (technical depth on demand, never forced). */
import { currentLocale, translate, useI18n } from '../../i18n'

/* Event types with an authored business phrase — exactly the canonical event
 * catalog the platform emits (GitHub connector + internal collaboration).
 * Unknown or custom types fall back to a generic phrase — no guessing from
 * prose, no raw codes for employees. */
const KNOWN = [
  'github.pull_request.opened', 'github.pull_request.closed', 'github.pull_request.merged',
  'github.issue.opened', 'github.issue.closed',
  'internal.peer.thanks', 'internal.manager.recognition', 'internal.help.completed',
] as const

export function eventPhrase(type: string | null | undefined, locale = currentLocale()): string {
  if (type && (KNOWN as readonly string[]).includes(type)) return translate(locale, 'provenance.event.' + type)
  return translate(locale, 'provenance.event.unknown')
}

export function EventPhrase({ type, showCode = false }: { type?: string | null; showCode?: boolean }) {
  const { locale } = useI18n()
  return (
    <>
      {eventPhrase(type, locale)}
      {showCode && !!type && <code className="dim" style={{ fontSize: 11, marginInlineStart: 6 }} dir="ltr">{type}</code>}
    </>
  )
}

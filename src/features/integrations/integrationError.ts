/* WS5 — integration configuration errors become human, actionable guidance.
 * Canonical backend codes stay on the wire (clients/tests depend on them);
 * the UI translates the safe known set and falls back to a generic message —
 * never raw stack traces, DB details or secret-bearing text. */
import { ApiError } from '../../api'
import { currentLocale, translate } from '../../i18n'

const KNOWN = ['CAPABILITY_DISABLED', 'WORKSPACE_CONFLICT', 'FORBIDDEN', 'NOT_FOUND',
  'VALIDATION', 'INGRESS_UNAVAILABLE', 'NETWORK']

export function integrationErrorText(error: unknown): string {
  const code = error instanceof ApiError ? error.code : 'NETWORK'
  return translate(currentLocale(),
    KNOWN.includes(code) ? `integrations.err.${code}` : 'integrations.error')
}

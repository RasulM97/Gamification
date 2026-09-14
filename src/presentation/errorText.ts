import { ApiError } from '../api'
import { currentLocale, translate } from '../i18n'

export function errorText(error: unknown): string {
  const code = error instanceof ApiError ? error.code : 'NETWORK'
  const known = ['FORBIDDEN', 'VALIDATION', 'NOT_FOUND', 'BAD_STATE', 'INSUFFICIENT_FUNDS',
    'REVIEW_AUTHORITY_REQUIRED', 'SENSITIVITY_CONFIRMATION_REQUIRED', 'USER_HAS_RESPONSIBILITIES',
    'SOLE_ADMIN', 'NETWORK', 'UPLOAD_REJECTED', 'OUT_OF_STOCK', 'LIMIT_REACHED', 'NO_CHANGE']
  return translate(currentLocale(), code === 'CAPACITY_REACHED' ? 'capacity.reached'
    : `integrity.error.${known.includes(code) ? code : 'VALIDATION'}`, error instanceof ApiError ? error.details : {})
}

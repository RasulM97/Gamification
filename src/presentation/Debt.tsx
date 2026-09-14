import { coinDebtOf } from '../domain/engine'
import { useStore } from '../store'
import { useI18n } from '../i18n'
import { coins } from '../ui'

export function Debt({ userId }: { userId: string }) {
  const { state } = useStore(), { t } = useI18n(), debt = coinDebtOf(state, userId)
  return debt > 0 ? <div className="neg" data-testid="coin-debt">{t('integrity.debt')}: {coins(debt)}</div> : null
}

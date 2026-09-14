import { useI18n } from '../i18n'

export function SensitivityGuard({ required, confirmed, onConfirm }: { required: boolean; confirmed: boolean; onConfirm: (value: boolean) => void }) {
  const { t } = useI18n()
  if (!required) return null
  return <div className="panel" style={{ padding: 14, marginBlock: 12 }} role="group" aria-label={t('integrity.sensitivityTitle')}>
    <p className="neg">{t('integrity.sensitivityWarning')}</p>
    <label><input type="checkbox" checked={confirmed} onChange={e => onConfirm(e.target.checked)} /> {t('integrity.sensitivityConfirm')}</label>
  </div>
}

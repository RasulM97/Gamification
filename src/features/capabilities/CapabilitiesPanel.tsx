import { useState } from 'react'
import { useStore } from '../../store'
import { IS_DEMO } from '../../runtime'
import { api } from '../../api'
import { useI18n } from '../../i18n'
import { Panel } from '../../ui'

const KEYS = ['TASK_LITE', 'RECOGNITION', 'THANKS', 'HELP', 'GITHUB_CONNECTOR', 'SHADOW_MODE', 'INCENTIVE_SAFETY'] as const

export function CapabilitiesPanel() {
  const { state, refresh } = useStore(), { t } = useI18n()
  const [busy, setBusy] = useState(false), [error, setError] = useState(false)
  const values = state.capabilities
  const toggle = async (key: string, enabled: boolean) => {
    setBusy(true); setError(false)
    try { await api.put(`/capabilities/${key}`, { enabled }); refresh() }
    catch { setError(true) }
    finally { setBusy(false) }
  }
  return <Panel title={t('capabilities.title')}>
    {IS_DEMO && <p>{t('capabilities.demo')}</p>}
    {!values && <p role="status">{t('capabilities.unavailable')}</p>}
    {error && <p role="alert">{t('capabilities.error')}</p>}
    {KEYS.map(key => <div key={key} style={{ display: 'flex', flexWrap: 'wrap', gap: 12, justifyContent: 'space-between', paddingBlock: 10 }}>
      <div><strong>{t(`capabilities.${key}`)}</strong><p>{t(`capabilities.${key}.description`)}</p></div>
      <button className="btn" type="button" aria-label={t(`capabilities.${key}`)}
        aria-pressed={values?.[key] === true}
        disabled={IS_DEMO || busy || typeof values?.[key] !== 'boolean' || key === 'INCENTIVE_SAFETY'}
        onClick={() => toggle(key, !values?.[key])}>
        {key === 'INCENTIVE_SAFETY' ? t('capabilities.required') : values?.[key] === true ? t('capabilities.enabled') : t('capabilities.disabled')}
      </button>
    </div>)}
  </Panel>
}

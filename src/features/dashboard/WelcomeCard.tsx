import { useState } from 'react'
import { useMe } from '../../store'
import { useI18n } from '../../i18n'

export function WelcomeCard() {
  const me = useMe()
  const { t } = useI18n()
  const key = 'cve-welcome-' + me.id
  const [show, setShow] = useState(() => { try { return !localStorage.getItem(key) } catch { return true } })
  if (!show) return null
  const dismiss = () => { try { localStorage.setItem(key, '1') } catch { /* ignore */ } setShow(false) }
  const steps = me.role === 'EMPLOYEE'
    ? [
        [t('welcome.employee1Title'), t('welcome.employee1Text')],
        [t('welcome.employee2Title'), t('welcome.employee2Text')],
        [t('welcome.employee3Title'), t('welcome.employee3Text')],
      ]
    : [
        [t('welcome.manager1Title'), t('welcome.manager1Text')],
        [t('welcome.manager2Title'), t('welcome.manager2Text')],
        [t('welcome.manager3Title'), t('welcome.manager3Text')],
      ]
  return (
    <div className="welcome">
      <button className="btn wdismiss" onClick={dismiss} aria-label={t('accessibility.dismissWelcome')}>{t('welcome.gotIt')}</button>
      <h3>{t(me.role === 'EMPLOYEE' ? 'welcome.titleEmployee' : 'welcome.titleManager', { name: me.name.split(' ')[0] })}</h3>
      <div className="wsub">{t('welcome.intro')}</div>
      <div className="wsteps">
        {steps.map(([b, s], i) => (
          <div className="wstep" key={i}><b><span className="wn">{i + 1}</span>{b}</b>{s}</div>
        ))}
      </div>
    </div>
  )
}

/* Generic webhook source configuration (WS5): the EXISTING E3 ingress gets
 * its missing management surface. Each source authenticates deliveries with
 * its own HMAC signature; receiving an event never authorizes a payout by
 * itself. Webhooks are not behind a capability flag — they are part of the
 * always-on intake surface, so this section has no capability lock. */
import { useState } from 'react'
import { useI18n } from '../../i18n'
import { Field, Modal, Panel } from '../../ui'
import { governance } from '../governance/source'
import { useGovData } from '../governance/hooks'
import type { WebhookSourceItem } from '../governance/types'
import { SecretOnce, RotateConfirm } from './SecretOnce'
import { integrationErrorText } from './integrationError'

function SourcePanel({ source, onChanged }: { source: WebhookSourceItem; onChanged: () => void }) {
  const { t } = useI18n()
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<unknown>(null)
  const [rotateOpen, setRotateOpen] = useState(false)
  const [secret, setSecret] = useState('')

  const run = async (work: () => Promise<unknown>) => {
    setBusy(true); setError(null)
    try { await work(); onChanged(); return true }
    catch (err) { setError(err); return false } finally { setBusy(false) }
  }
  const toggle = () => run(() => governance.setWebhookSourceActive(source.id, !source.active))
  const rotate = () => run(async () => {
    const result = await governance.rotateWebhookSecret(source.id)
    if (result.secret) { setSecret(result.secret); setRotateOpen(false) }
  })

  return (
    <Panel title={<span dir="auto">{source.name}</span>} right={
      <span style={{ display: 'inline-flex', gap: 8, alignItems: 'center' }}>
        <span className={'bd ' + (source.active ? 'bd-normal' : 'bd-none')}>
          {t(source.active ? 'common.active' : 'common.inactive')}</span>
        <button className="btn" disabled={busy} onClick={() => setRotateOpen(true)}>
          {t('integrations.action.rotate')}</button>
        <button className="btn" disabled={busy} onClick={toggle}>
          {t(source.active ? 'integrations.action.disable' : 'integrations.action.enable')}</button>
      </span>}>
      {error != null && <p role="alert">{integrationErrorText(error)}</p>}
      <p className="dim" style={{ fontSize: 12.5 }}>
        {t('integrations.webhook.deliveryPath')} <code dir="ltr">/api/webhooks/{source.sourceKey}/events</code>
      </p>
      <p className="dim" style={{ fontSize: 12 }}>
        {t('integrations.credential')}: {t('integrations.credentialConfigured')}
      </p>
      {secret && <SecretOnce secret={secret} onDismiss={() => setSecret('')} />}
      <RotateConfirm open={rotateOpen} busy={busy} onCancel={() => setRotateOpen(false)} onConfirm={rotate} />
    </Panel>
  )
}

export function WebhookSection() {
  const { t } = useI18n()
  const sources = useGovData(() => governance.listWebhookSources())
  const [createOpen, setCreateOpen] = useState(false)
  const [name, setName] = useState('')
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<unknown>(null)
  const [secret, setSecret] = useState('')

  const create = async () => {
    setBusy(true); setError(null)
    try {
      const result = await governance.createWebhookSource(name.trim())
      if (result.secret) setSecret(result.secret)
      setName(''); setCreateOpen(false); sources.reload()
    } catch (err) { setError(err) } finally { setBusy(false) }
  }

  return (
    <section data-testid="integrations-webhook">
      <div className="dsec" style={{ marginTop: 18 }}>
        <span className="eyebrow">{t('integrations.webhook.title')}</span>{' '}
        <span className="bd bd-normal">
          {t('integrations.capability')}: {t('integrations.capabilityAlways')}</span>
        <p className="dim" style={{ fontSize: 12 }}>{t('integrations.webhook.hint')}</p>
        {sources.data && sources.data.length === 0 &&
          <p className="dim" style={{ fontSize: 12.5 }}>{t('integrations.connectionNone')}</p>}
      </div>
      {sources.error != null && (
        <p role="alert">{integrationErrorText(sources.error)}{' '}
          <button className="btn" onClick={sources.reload}>{t('incentives.retry')}</button></p>
      )}
      {sources.data?.map(s => <SourcePanel key={s.id} source={s} onChanged={sources.reload} />)}
      {secret && <SecretOnce secret={secret} onDismiss={() => setSecret('')} />}
      <button className="btn" onClick={() => { setCreateOpen(true); setSecret('') }}>
        + {t('integrations.webhook.create')}</button>

      <Modal open={createOpen} onClose={() => setCreateOpen(false)} title={t('integrations.webhook.create')}>
        {error != null && <p role="alert">{integrationErrorText(error)}</p>}
        <Field label={t('integrations.github.name')}>
          <input value={name} maxLength={120} onChange={e => setName(e.target.value)} autoFocus />
        </Field>
        <div className="actionbar" style={{ position: 'static', margin: '4px -18px -18px' }}>
          <button className="btn" onClick={() => setCreateOpen(false)}>{t('common.cancel')}</button>
          <button className="btn primary" disabled={busy || !name.trim()} onClick={create}>
            {t('common.saveChanges')}</button>
        </div>
      </Modal>
    </section>
  )
}

/* Slack connector configuration (WS5): workspace binding, signing-secret
 * rotation, status, and explicit identity mapping for the EXISTING connector.
 * Slack stays authoritative for Slack work — CVE only receives signed slash
 * commands. The signing secret is shown exactly once after create/rotate; the
 * backend stores only the derivation nonce, so a lost secret means rotate.
 * `locked` means the SLACK_CONNECTOR capability is disabled: connections and
 * credentials stay visible truthfully, but management actions are withheld
 * (the backend would refuse them with 409 CAPABILITY_DISABLED). */
import { useState } from 'react'
import { useStore } from '../../store'
import { useI18n } from '../../i18n'
import { Field, Modal, Panel } from '../../ui'
import { governance } from '../governance/source'
import { useGovData } from '../governance/hooks'
import type { SlackWorkspaceItem } from '../governance/types'
import { SecretOnce, RotateConfirm } from './SecretOnce'
import { integrationErrorText } from './integrationError'

function WorkspacePanel({ workspace, locked, lockHint, onChanged }: {
  workspace: SlackWorkspaceItem; locked: boolean; lockHint: string; onChanged: () => void
}) {
  const { state } = useStore()
  const { t } = useI18n()
  const identities = useGovData(() => governance.listSlackIdentities(workspace.id), [workspace.id])
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<unknown>(null)
  const [mapOpen, setMapOpen] = useState(false)
  const [rotateOpen, setRotateOpen] = useState(false)
  const [secret, setSecret] = useState('')
  const [externalId, setExternalId] = useState('')
  const [mapUser, setMapUser] = useState('')
  const name = (id: string) => state.users.find(u => u.id === id)?.name ?? id

  /* run() reports success so the mapping modal closes/resets ONLY after a
     successful mutation — a failure keeps the Admin's entered values and
     shows the mapped, localized error inside the modal. */
  const run = async (work: () => Promise<unknown>) => {
    setBusy(true); setError(null)
    try { await work(); identities.reload(); onChanged(); return true }
    catch (err) { setError(err); return false } finally { setBusy(false) }
  }
  const toggle = () => run(() =>
    governance.setSlackWorkspaceStatus(workspace.id, workspace.status === 'ACTIVE' ? 'DISABLED' : 'ACTIVE'))
  const rotate = () => run(async () => {
    const result = await governance.rotateSlackSecret(workspace.id)
    if (result.secret) { setSecret(result.secret); setRotateOpen(false) }
  })

  return (
    <Panel title={<span dir="auto">{workspace.name}</span>} right={
      <span style={{ display: 'inline-flex', gap: 8, alignItems: 'center' }}>
        <span className={'bd ' + (workspace.status === 'ACTIVE' ? 'bd-normal' : 'bd-none')}>
          {t(workspace.status === 'ACTIVE' ? 'common.active' : 'common.inactive')}</span>
        <button className="btn" disabled={busy || locked} title={locked ? lockHint : ''}
          onClick={() => setRotateOpen(true)}>{t('integrations.action.rotate')}</button>
        <button className="btn" disabled={busy || locked} title={locked ? lockHint : ''} onClick={toggle}>
          {t(workspace.status === 'ACTIVE' ? 'integrations.action.disable' : 'integrations.action.enable')}</button>
      </span>}>
      {error != null && <p role="alert">{integrationErrorText(error)}</p>}
      <p className="dim" style={{ fontSize: 12.5 }}>
        {t('integrations.slack.teamId')} <code dir="ltr">{workspace.externalTeamId}</code> · {t('integrations.slack.commandPath')} <code dir="ltr">{workspace.commandPath}</code>
      </p>
      <p className="dim" style={{ fontSize: 12 }}>{t('integrations.slack.hint')}</p>
      <p className="dim" style={{ fontSize: 12 }}>
        {t('integrations.credential')}: {t('integrations.credentialConfigured')}
      </p>
      {secret && <SecretOnce secret={secret} onDismiss={() => setSecret('')} />}
      <RotateConfirm open={rotateOpen} busy={busy} onCancel={() => setRotateOpen(false)} onConfirm={rotate} />

      <div className="dsec">
        <span className="eyebrow">{t('integrations.identities')}</span>
        {identities.data && identities.data.length === 0 &&
          <p className="dim" style={{ fontSize: 12.5 }}>{t('integrations.identitiesEmpty')}</p>}
        {identities.data?.map(m => (
          <div key={m.externalUserId} style={{ display: 'flex', gap: 8, paddingBlock: 4, alignItems: 'center' }}>
            <code dir="ltr">{m.externalUserId}</code> → <b dir="auto">{name(m.userId)}</b>
            <button className="btn" style={{ marginInlineStart: 'auto', padding: '2px 10px', fontSize: 11.5 }}
              disabled={busy || locked} title={locked ? lockHint : t('integrations.removeMappingHint')}
              onClick={() => run(() => governance.deleteSlackIdentity(workspace.id, m.externalUserId))}>
              {t('integrations.action.removeMapping')}</button>
          </div>
        ))}
        <button className="btn" style={{ marginTop: 8 }} disabled={locked} title={locked ? lockHint : ''}
          onClick={() => setMapOpen(true)}>+ {t('integrations.mapIdentity')}</button>
      </div>

      <Modal open={mapOpen} onClose={() => setMapOpen(false)} title={t('integrations.mapIdentity')}>
        {error != null && <p role="alert">{integrationErrorText(error)}</p>}
        <Field label={t('integrations.externalId')}>
          <input dir="ltr" value={externalId} autoFocus
            onChange={e => setExternalId(e.target.value.toUpperCase().replace(/[^A-Z0-9]/g, ''))} />
        </Field>
        <Field label={t('common.person')}>
          <select value={mapUser} onChange={e => setMapUser(e.target.value)}>
            <option value="">{t('integrations.selectUser')}</option>
            {state.users.filter(u => u.active !== false && !u.activationPending).map(u =>
              <option key={u.id} value={u.id}>{u.name}</option>)}
          </select>
        </Field>
        <div className="actionbar" style={{ position: 'static', margin: '4px -18px -18px' }}>
          <button className="btn" onClick={() => setMapOpen(false)}>{t('common.cancel')}</button>
          <button className="btn primary" disabled={busy || !externalId || !mapUser} onClick={() =>
            run(() => governance.mapSlackIdentity(workspace.id, externalId, mapUser))
              .then(ok => { if (!ok) return; setMapOpen(false); setExternalId(''); setMapUser('') })}>
            {t('common.saveChanges')}</button>
        </div>
      </Modal>
    </Panel>
  )
}

export function SlackSection({ locked, lockHint }: { locked: boolean; lockHint: string }) {
  const { t } = useI18n()
  const workspaces = useGovData(() => governance.listSlackWorkspaces())
  const [createOpen, setCreateOpen] = useState(false)
  const [wsName, setWsName] = useState('')
  const [teamId, setTeamId] = useState('')
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<unknown>(null)
  const [secret, setSecret] = useState('')

  const create = async () => {
    setBusy(true); setError(null)
    try {
      const result = await governance.createSlackWorkspace(wsName.trim(), teamId)
      if (result.secret) setSecret(result.secret)
      setWsName(''); setTeamId(''); setCreateOpen(false); workspaces.reload()
    } catch (err) { setError(err) } finally { setBusy(false) }
  }

  return (
    <section data-testid="integrations-slack">
      <div className="dsec" style={{ marginTop: 18 }}>
        <span className="eyebrow">{t('integrations.slack.title')}</span>{' '}
        <span className={'bd ' + (locked ? 'bd-none' : 'bd-normal')}>
          {t('integrations.capability')}: {t(locked ? 'integrations.state.disabled' : 'integrations.state.enabled')}</span>
        {locked && <p className="dim" style={{ fontSize: 12 }}>{lockHint}</p>}
        {workspaces.data && workspaces.data.length === 0 &&
          <p className="dim" style={{ fontSize: 12.5 }}>{t('integrations.connectionNone')}</p>}
      </div>
      {workspaces.error != null && (
        <p role="alert">{integrationErrorText(workspaces.error)}{' '}
          <button className="btn" onClick={workspaces.reload}>{t('incentives.retry')}</button></p>
      )}
      {workspaces.data?.map(w => (
        <WorkspacePanel key={w.id} workspace={w} locked={locked} lockHint={lockHint}
          onChanged={workspaces.reload} />
      ))}
      {secret && <SecretOnce secret={secret} onDismiss={() => setSecret('')} />}
      <button className="btn" disabled={locked} title={locked ? lockHint : ''}
        onClick={() => { setCreateOpen(true); setSecret('') }}>
        + {t('integrations.slack.create')}</button>

      <Modal open={createOpen} onClose={() => setCreateOpen(false)} title={t('integrations.slack.create')}>
        {error != null && <p role="alert">{integrationErrorText(error)}</p>}
        <Field label={t('integrations.slack.workspaceName')}>
          <input value={wsName} maxLength={120} onChange={e => setWsName(e.target.value)} autoFocus />
        </Field>
        <Field label={t('integrations.slack.teamId')}>
          <input dir="ltr" value={teamId} maxLength={20}
            onChange={e => setTeamId(e.target.value.toUpperCase().replace(/[^A-Z0-9]/g, ''))} />
        </Field>
        <div className="actionbar" style={{ position: 'static', margin: '4px -18px -18px' }}>
          <button className="btn" onClick={() => setCreateOpen(false)}>{t('common.cancel')}</button>
          <button className="btn primary" disabled={busy || !wsName.trim() || teamId.length < 6}
            onClick={create}>
            {t('common.saveChanges')}</button>
        </div>
      </Modal>
    </section>
  )
}

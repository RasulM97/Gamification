/* GitHub connector configuration (WS5): create + status + rotation + identity
 * mapping + resource→Project attribution for the EXISTING E9 connector.
 * GitHub stays authoritative for GitHub work — no issue/PR duplication.
 * `locked` means the GITHUB_CONNECTOR capability is disabled: connections and
 * credentials stay visible truthfully, but management actions are withheld
 * (the backend would refuse them with 409 CAPABILITY_DISABLED). */
import { useState } from 'react'
import { useStore } from '../../store'
import { useI18n } from '../../i18n'
import { Field, Modal, Panel, ago } from '../../ui'
import { governance } from '../governance/source'
import { useGovData } from '../governance/hooks'
import type { GithubSourceItem } from '../governance/types'
import { SecretOnce, RotateConfirm } from './SecretOnce'
import { integrationErrorText } from './integrationError'

function SourcePanel({ source, projects, locked, lockHint, onChanged }: {
  source: GithubSourceItem; projects: { id: string; name: string }[]
  locked: boolean; lockHint: string; onChanged: () => void
}) {
  const { state } = useStore()
  const { t } = useI18n()
  const identities = useGovData(() => governance.listGithubIdentities(source.id), [source.id])
  const attributions = useGovData(() => governance.listGithubAttributions(source.id), [source.id])
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<unknown>(null)
  const [mapOpen, setMapOpen] = useState(false)
  const [assignOpen, setAssignOpen] = useState(false)
  const [rotateOpen, setRotateOpen] = useState(false)
  const [secret, setSecret] = useState('')
  const [externalId, setExternalId] = useState('')
  const [mapUser, setMapUser] = useState('')
  const [kind, setKind] = useState<'issue' | 'pull_request'>('pull_request')
  const [resourceId, setResourceId] = useState('')
  const [projectId, setProjectId] = useState('')
  const name = (id: string) => state.users.find(u => u.id === id)?.name ?? id
  const projectName = (id: string | null) =>
    id === null ? t('integrations.companyScope') : (projects.find(p => p.id === id)?.name ?? id)

  const run = async (work: () => Promise<unknown>) => {
    setBusy(true); setError(null)
    try { await work(); identities.reload(); attributions.reload(); onChanged() }
    catch (err) { setError(err) } finally { setBusy(false) }
  }
  const toggle = () => run(() =>
    governance.setGithubSourceStatus(source.id, source.status === 'ACTIVE' ? 'DISABLED' : 'ACTIVE'))
  const rotate = () => run(async () => {
    const result = await governance.rotateGithubSecret(source.id)
    if (result.secret) { setSecret(result.secret); setRotateOpen(false) }
  })

  return (
    <Panel title={<span dir="auto">{source.name}</span>} right={
      <span style={{ display: 'inline-flex', gap: 8, alignItems: 'center' }}>
        <span className={'bd ' + (source.status === 'ACTIVE' ? 'bd-normal' : 'bd-none')}>
          {t(source.status === 'ACTIVE' ? 'common.active' : 'common.inactive')}</span>
        <button className="btn" disabled={busy || locked} title={locked ? lockHint : ''}
          onClick={() => setRotateOpen(true)}>{t('integrations.action.rotate')}</button>
        <button className="btn" disabled={busy || locked} title={locked ? lockHint : ''} onClick={toggle}>
          {t(source.status === 'ACTIVE' ? 'integrations.action.disable' : 'integrations.action.enable')}</button>
      </span>}>
      {error != null && <p role="alert">{integrationErrorText(error)}</p>}
      <p className="dim" style={{ fontSize: 12.5 }}>
        {t('integrations.repository')} <code>{source.repositoryId}</code> · {t('integrations.webhook')} <code dir="ltr">{source.webhookPath}</code>
      </p>
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
              onClick={() => run(() => governance.deleteGithubIdentity(source.id, m.externalUserId))}>
              {t('integrations.action.removeMapping')}</button>
          </div>
        ))}
        <button className="btn" style={{ marginTop: 8 }} disabled={locked} title={locked ? lockHint : ''}
          onClick={() => setMapOpen(true)}>+ {t('integrations.mapIdentity')}</button>
      </div>

      <div className="dsec">
        <span className="eyebrow">{t('integrations.attribution')}</span>
        <p className="dim" style={{ fontSize: 12 }}>{t('integrations.attributionNote')}</p>
        {attributions.data && attributions.data.length === 0 &&
          <p className="dim" style={{ fontSize: 12.5 }}>{t('integrations.attributionEmpty')}</p>}
        {attributions.data?.map(a => (
          <div key={a.id} style={{ display: 'flex', gap: 8, paddingBlock: 4, alignItems: 'center', flexWrap: 'wrap' }}>
            <span className="bd bd-none">{t('integrations.kind.' + a.resourceKind)}</span>
            <code dir="ltr">#{a.resourceId}</code> → <b dir="auto">{projectName(a.effectiveUntil === null ? a.projectId : null)}</b>
            <span className="dim" style={{ fontSize: 11.5 }}>
              {ago(a.effectiveFrom)}{a.effectiveUntil !== null && <> – {ago(a.effectiveUntil)}</>}
            </span>
          </div>
        ))}
        <button className="btn" style={{ marginTop: 8 }} disabled={projects.length === 0 || locked}
          title={locked ? lockHint : ''}
          onClick={() => setAssignOpen(true)}>+ {t('integrations.assignResource')}</button>
      </div>

      <Modal open={mapOpen} onClose={() => setMapOpen(false)} title={t('integrations.mapIdentity')}>
        <Field label={t('integrations.externalId')}>
          <input dir="ltr" inputMode="numeric" value={externalId} onChange={e => setExternalId(e.target.value.replace(/\D/g, ''))} autoFocus />
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
            run(() => governance.mapGithubIdentity(source.id, externalId, mapUser))
              .then(ok => { setMapOpen(false); setExternalId(''); setMapUser(''); return ok })}>
            {t('common.saveChanges')}</button>
        </div>
      </Modal>

      <Modal open={assignOpen} onClose={() => setAssignOpen(false)} title={t('integrations.assignResource')}>
        <Field label={t('common.type')}>
          <select value={kind} onChange={e => setKind(e.target.value as typeof kind)}>
            <option value="pull_request">{t('integrations.kind.pull_request')}</option>
            <option value="issue">{t('integrations.kind.issue')}</option>
          </select>
        </Field>
        <Field label={t('integrations.resourceId')}>
          <input dir="ltr" inputMode="numeric" value={resourceId} onChange={e => setResourceId(e.target.value.replace(/\D/g, ''))} />
        </Field>
        <Field label={t('organization.PROJECT')}>
          <select value={projectId} onChange={e => setProjectId(e.target.value)}>
            <option value="">{t('integrations.companyScope')}</option>
            {projects.map(p => <option key={p.id} value={p.id}>{p.name}</option>)}
          </select>
        </Field>
        <div className="actionbar" style={{ position: 'static', margin: '4px -18px -18px' }}>
          <button className="btn" onClick={() => setAssignOpen(false)}>{t('common.cancel')}</button>
          <button className="btn primary" disabled={busy || !resourceId} onClick={() =>
            run(() => governance.assignGithubResource(source.id, kind, resourceId, projectId || null))
              .then(ok => { setAssignOpen(false); setResourceId(''); setProjectId(''); return ok })}>
            {t('common.saveChanges')}</button>
        </div>
      </Modal>
    </Panel>
  )
}

export function GithubSection({ locked, lockHint }: { locked: boolean; lockHint: string }) {
  const { t } = useI18n()
  const sources = useGovData(() => governance.listGithubSources())
  const units = useGovData(() => governance.listOrgUnits())
  const [createOpen, setCreateOpen] = useState(false)
  const [name, setName] = useState('')
  const [repositoryId, setRepositoryId] = useState('')
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<unknown>(null)
  const [secret, setSecret] = useState('')
  const projects = (units.data ?? []).filter(u => u.kind === 'PROJECT' && u.status === 'ACTIVE')
    .map(u => ({ id: u.id, name: u.name }))

  const create = async () => {
    setBusy(true); setError(null)
    try {
      const result = await governance.createGithubSource(name.trim(), repositoryId)
      if (result.secret) setSecret(result.secret)
      setName(''); setRepositoryId(''); setCreateOpen(false); sources.reload()
    } catch (err) { setError(err) } finally { setBusy(false) }
  }

  return (
    <section data-testid="integrations-github">
      <div className="dsec" style={{ marginTop: 18 }}>
        <span className="eyebrow">{t('integrations.github.title')}</span>{' '}
        <span className={'bd ' + (locked ? 'bd-none' : 'bd-normal')}>
          {t('integrations.capability')}: {t(locked ? 'integrations.state.disabled' : 'integrations.state.enabled')}</span>
        <p className="dim" style={{ fontSize: 12 }}>{t('integrations.github.hint')}</p>
        {locked && <p className="dim" style={{ fontSize: 12 }}>{lockHint}</p>}
        {sources.data && sources.data.length === 0 &&
          <p className="dim" style={{ fontSize: 12.5 }}>{t('integrations.connectionNone')}</p>}
      </div>
      {sources.error != null && (
        <p role="alert">{integrationErrorText(sources.error)}{' '}
          <button className="btn" onClick={sources.reload}>{t('incentives.retry')}</button></p>
      )}
      {sources.data?.map(s => (
        <SourcePanel key={s.id} source={s} projects={projects} locked={locked} lockHint={lockHint}
          onChanged={sources.reload} />
      ))}
      {secret && <SecretOnce secret={secret} onDismiss={() => setSecret('')} />}
      <button className="btn" disabled={locked} title={locked ? lockHint : ''}
        onClick={() => { setCreateOpen(true); setSecret('') }}>
        + {t('integrations.github.create')}</button>

      <Modal open={createOpen} onClose={() => setCreateOpen(false)} title={t('integrations.github.create')}>
        {error != null && <p role="alert">{integrationErrorText(error)}</p>}
        <Field label={t('integrations.github.name')}>
          <input value={name} maxLength={120} onChange={e => setName(e.target.value)} autoFocus />
        </Field>
        <Field label={t('integrations.github.repositoryId')} hint={t('integrations.github.repositoryIdHint')}>
          <input dir="ltr" inputMode="numeric" value={repositoryId}
            onChange={e => setRepositoryId(e.target.value.replace(/\D/g, ''))} />
        </Field>
        <div className="actionbar" style={{ position: 'static', margin: '4px -18px -18px' }}>
          <button className="btn" onClick={() => setCreateOpen(false)}>{t('common.cancel')}</button>
          <button className="btn primary" disabled={busy || !name.trim() || !repositoryId} onClick={create}>
            {t('common.saveChanges')}</button>
        </div>
      </Modal>
    </section>
  )
}

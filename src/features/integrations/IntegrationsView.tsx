/* Integrations view (Cohesion F2) — GitHub connector management: sources,
 * identity mapping, and resource→Project attribution. Admin-only (the
 * backend enforces it; the nav gates it). Unattributed resources stay
 * company-scoped — the UI says so explicitly instead of implying inference.
 * Demo mode runs on the deterministic fixtures; server mode on the real API. */
import { useState } from 'react'
import { useStore } from '../../store'
import { useI18n } from '../../i18n'
import { Empty, Field, Modal, Panel, ago } from '../../ui'
import { governance } from '../governance/source'
import { useGovData } from '../governance/hooks'
import type { GithubSourceItem, SlackWorkspaceItem } from '../governance/types'

function SourcePanel({ source, projects }: {
  source: GithubSourceItem; projects: { id: string; name: string }[]
}) {
  const { state } = useStore()
  const { t } = useI18n()
  const identities = useGovData(() => governance.listGithubIdentities(source.id), [source.id])
  const attributions = useGovData(() => governance.listGithubAttributions(source.id), [source.id])
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState(false)
  const [mapOpen, setMapOpen] = useState(false)
  const [assignOpen, setAssignOpen] = useState(false)
  const [externalId, setExternalId] = useState('')
  const [mapUser, setMapUser] = useState('')
  const [kind, setKind] = useState<'issue' | 'pull_request'>('pull_request')
  const [resourceId, setResourceId] = useState('')
  const [projectId, setProjectId] = useState('')
  const name = (id: string) => state.users.find(u => u.id === id)?.name ?? id
  const projectName = (id: string | null) =>
    id === null ? t('integrations.companyScope') : (projects.find(p => p.id === id)?.name ?? id)

  const run = async (work: () => Promise<unknown>) => {
    setBusy(true); setError(false)
    try { await work(); identities.reload(); attributions.reload() }
    catch { setError(true) } finally { setBusy(false) }
  }
  const toggle = () => run(() =>
    governance.setGithubSourceStatus(source.id, source.status === 'ACTIVE' ? 'DISABLED' : 'ACTIVE'))

  return (
    <Panel title={<span dir="auto">{source.name}</span>} right={
      <span style={{ display: 'inline-flex', gap: 8, alignItems: 'center' }}>
        <span className={'bd ' + (source.status === 'ACTIVE' ? 'bd-normal' : 'bd-none')}>
          {t(source.status === 'ACTIVE' ? 'common.active' : 'common.inactive')}</span>
        <button className="btn" disabled={busy} onClick={toggle}>
          {t(source.status === 'ACTIVE' ? 'integrations.action.disable' : 'integrations.action.enable')}</button>
      </span>}>
      {error && <p role="alert">{t('integrations.error')}</p>}
      <p className="dim" style={{ fontSize: 12.5 }}>
        {t('integrations.repository')} <code>{source.repositoryId}</code> · {t('integrations.webhook')} <code dir="ltr">{source.webhookPath}</code>
      </p>

      <div className="dsec">
        <span className="eyebrow">{t('integrations.identities')}</span>
        {identities.data && identities.data.length === 0 &&
          <p className="dim" style={{ fontSize: 12.5 }}>{t('integrations.identitiesEmpty')}</p>}
        {identities.data?.map(m => (
          <div key={m.externalUserId} style={{ display: 'flex', gap: 8, paddingBlock: 4, alignItems: 'center' }}>
            <code dir="ltr">{m.externalUserId}</code> → <b dir="auto">{name(m.userId)}</b>
          </div>
        ))}
        <button className="btn" style={{ marginTop: 8 }} onClick={() => setMapOpen(true)}>
          + {t('integrations.mapIdentity')}</button>
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
        <button className="btn" style={{ marginTop: 8 }} disabled={projects.length === 0}
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

/* WS1 Slack intake: workspace binding + explicit identity mapping. The signing
 * secret is shown exactly once after create/rotate — the backend stores only
 * the derivation nonce, so a lost secret means rotate, never retrieve. */
function SlackPanel({ workspace }: { workspace: SlackWorkspaceItem }) {
  const { state } = useStore()
  const { t } = useI18n()
  const identities = useGovData(() => governance.listSlackIdentities(workspace.id), [workspace.id])
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState(false)
  const [mapOpen, setMapOpen] = useState(false)
  const [externalId, setExternalId] = useState('')
  const [mapUser, setMapUser] = useState('')
  const [secret, setSecret] = useState('')
  const name = (id: string) => state.users.find(u => u.id === id)?.name ?? id

  const run = async (work: () => Promise<unknown>) => {
    setBusy(true); setError(false)
    try { await work(); identities.reload() }
    catch { setError(true) } finally { setBusy(false) }
  }
  const toggle = () => run(() =>
    governance.setSlackWorkspaceStatus(workspace.id, workspace.status === 'ACTIVE' ? 'DISABLED' : 'ACTIVE'))
  const rotate = () => run(async () => {
    const result = await governance.rotateSlackSecret(workspace.id)
    if (result.secret) setSecret(result.secret)
  })

  return (
    <Panel title={<span dir="auto">{workspace.name}</span>} right={
      <span style={{ display: 'inline-flex', gap: 8, alignItems: 'center' }}>
        <span className={'bd ' + (workspace.status === 'ACTIVE' ? 'bd-normal' : 'bd-none')}>
          {t(workspace.status === 'ACTIVE' ? 'common.active' : 'common.inactive')}</span>
        <button className="btn" disabled={busy} onClick={rotate}>{t('integrations.action.rotate')}</button>
        <button className="btn" disabled={busy} onClick={toggle}>
          {t(workspace.status === 'ACTIVE' ? 'integrations.action.disable' : 'integrations.action.enable')}</button>
      </span>}>
      {error && <p role="alert">{t('integrations.error')}</p>}
      <p className="dim" style={{ fontSize: 12.5 }}>
        {t('integrations.slack.teamId')} <code dir="ltr">{workspace.externalTeamId}</code> · {t('integrations.slack.commandPath')} <code dir="ltr">{workspace.commandPath}</code>
      </p>
      <p className="dim" style={{ fontSize: 12 }}>{t('integrations.slack.hint')}</p>
      {secret && <p role="status" style={{ fontSize: 12.5 }}>
        {t('integrations.slack.secretOnce')} <code dir="ltr">{secret}</code></p>}

      <div className="dsec">
        <span className="eyebrow">{t('integrations.identities')}</span>
        {identities.data && identities.data.length === 0 &&
          <p className="dim" style={{ fontSize: 12.5 }}>{t('integrations.identitiesEmpty')}</p>}
        {identities.data?.map(m => (
          <div key={m.externalUserId} style={{ display: 'flex', gap: 8, paddingBlock: 4, alignItems: 'center' }}>
            <code dir="ltr">{m.externalUserId}</code> → <b dir="auto">{name(m.userId)}</b>
          </div>
        ))}
        <button className="btn" style={{ marginTop: 8 }} onClick={() => setMapOpen(true)}>
          + {t('integrations.mapIdentity')}</button>
      </div>

      <Modal open={mapOpen} onClose={() => setMapOpen(false)} title={t('integrations.mapIdentity')}>
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
              .then(ok => { setMapOpen(false); setExternalId(''); setMapUser(''); return ok })}>
            {t('common.saveChanges')}</button>
        </div>
      </Modal>
    </Panel>
  )
}

export function IntegrationsView() {
  const { t } = useI18n()
  const sources = useGovData(() => governance.listGithubSources())
  const slack = useGovData(() => governance.listSlackWorkspaces())
  const units = useGovData(() => governance.listOrgUnits())
  const [createOpen, setCreateOpen] = useState(false)
  const [wsName, setWsName] = useState('')
  const [teamId, setTeamId] = useState('')
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState(false)
  const [secret, setSecret] = useState('')
  const projects = (units.data ?? []).filter(u => u.kind === 'PROJECT' && u.status === 'ACTIVE')
    .map(u => ({ id: u.id, name: u.name }))
  const empty = sources.data?.length === 0 && slack.data?.length === 0
  const create = async () => {
    setBusy(true); setError(false)
    try {
      const result = await governance.createSlackWorkspace(wsName.trim(), teamId)
      if (result.secret) setSecret(result.secret)
      setWsName(''); setTeamId(''); slack.reload()
      return true
    } catch { setError(true); return false } finally { setBusy(false) }
  }
  return (
    <div className="wrap">
      {sources.loading && <p role="status">{t('common.loading')}</p>}
      {sources.error && <p role="alert">{t('integrations.error')} <button className="btn" onClick={sources.reload}>{t('incentives.retry')}</button></p>}
      {empty &&
        <Empty title={t('integrations.empty')} hint={t('integrations.emptyHint')} />}
      {sources.data?.map(s => <SourcePanel key={s.id} source={s} projects={projects} />)}

      <div className="dsec" style={{ marginTop: 18 }}>
        <span className="eyebrow">{t('integrations.slack.title')}</span>
      </div>
      {slack.error && <p role="alert">{t('integrations.error')} <button className="btn" onClick={slack.reload}>{t('incentives.retry')}</button></p>}
      {slack.data?.map(w => <SlackPanel key={w.id} workspace={w} />)}
      <button className="btn" onClick={() => { setCreateOpen(true); setSecret('') }}>
        + {t('integrations.slack.create')}</button>
      {secret && <p role="status" style={{ fontSize: 12.5 }}>
        {t('integrations.slack.secretOnce')} <code dir="ltr">{secret}</code></p>}

      <Modal open={createOpen} onClose={() => setCreateOpen(false)} title={t('integrations.slack.create')}>
        {error && <p role="alert">{t('integrations.error')}</p>}
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
            onClick={() => create().then(ok => { if (ok) setCreateOpen(false) })}>
            {t('common.saveChanges')}</button>
        </div>
      </Modal>
    </div>
  )
}

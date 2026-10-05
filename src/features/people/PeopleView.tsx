/* People view (Cohesion F1/E8) — Thanks, Recognition and Help as one
 * product surface. Server mode calls the collaboration API; demo mode uses
 * the deterministic fixtures. Capability-disabled sections render an
 * explicit disabled state instead of vanishing silently (§6). */
import { useState } from 'react'
import { useStore, useMe } from '../../store'
import { useI18n } from '../../i18n'
import { Avatar, Empty, Field, Modal, Panel, Seg, ago } from '../../ui'
import { governance } from '../governance/source'
import { useGovData } from '../governance/hooks'

function GiveForm({ kind, onDone }: { kind: 'thanks' | 'recognition'; onDone: () => void }) {
  const { state, meId } = useStore()
  const { t } = useI18n()
  const [open, setOpen] = useState(false)
  const [to, setTo] = useState('')
  const [message, setMessage] = useState('')
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState(false)
  const recipients = state.users.filter(u => u.id !== meId && u.active !== false && !u.activationPending)
  const submit = async () => {
    setBusy(true); setError(false)
    try {
      if (kind === 'thanks') await governance.giveThanks(to, message.trim(), meId)
      else await governance.recognize(to, message.trim(), meId)
      setOpen(false); setTo(''); setMessage(''); onDone()
    } catch { setError(true) } finally { setBusy(false) }
  }
  return (
    <>
      <button className="btn primary" onClick={() => setOpen(true)}>
        + {t(kind === 'thanks' ? 'people.giveThanks' : 'people.giveRecognition')}</button>
      <Modal open={open} onClose={() => setOpen(false)}
        title={t(kind === 'thanks' ? 'people.giveThanks' : 'people.giveRecognition')}>
        {error && <p role="alert">{t('people.error')}</p>}
        <Field label={t('people.recipient')}>
          <select value={to} onChange={e => setTo(e.target.value)} autoFocus>
            <option value="">{t('people.selectRecipient')}</option>
            {recipients.map(u => <option key={u.id} value={u.id}>{u.name}</option>)}
          </select>
        </Field>
        <Field label={t('people.message')}>
          <textarea dir={message ? 'auto' : undefined} value={message} maxLength={1000}
            onChange={e => setMessage(e.target.value)} />
        </Field>
        <div className="actionbar" style={{ position: 'static', margin: '4px -18px -18px' }}>
          <button className="btn" onClick={() => setOpen(false)}>{t('common.cancel')}</button>
          <button className="btn primary" disabled={busy || !to || !message.trim()} onClick={submit}>
            {t('people.send')}</button>
        </div>
      </Modal>
    </>
  )
}

export function PeopleView() {
  const { state, meId } = useStore()
  const me = useMe()
  const { t } = useI18n()
  const caps = state.capabilities ?? {}
  const [tab, setTab] = useState<'thanks' | 'recognition' | 'help'>('thanks')
  const enabled = {
    thanks: caps.THANKS !== false, recognition: caps.RECOGNITION !== false, help: caps.HELP !== false,
  }
  const tabs = (['thanks', 'recognition', 'help'] as const).filter(k => enabled[k])
  const active = tabs.includes(tab) ? tab : (tabs[0] ?? 'thanks')
  const canRecognize = me.role !== 'EMPLOYEE'

  const appreciation = useGovData(
    () => active === 'help' ? Promise.resolve([]) : governance.listAppreciation(active, meId),
    [active, meId])
  const help = useGovData(
    () => active === 'help' ? governance.listHelp() : Promise.resolve([]), [active])
  const name = (id?: string | null) =>
    id ? (state.users.find(u => u.id === id)?.name ?? id) : '—'
  const [helpOpen, setHelpOpen] = useState(false)
  const [helpTitle, setHelpTitle] = useState('')
  const [helpDesc, setHelpDesc] = useState('')
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState(false)

  const submitHelp = async () => {
    setBusy(true); setError(false)
    try {
      await governance.requestHelp(helpTitle.trim(), helpDesc.trim(), meId)
      setHelpOpen(false); setHelpTitle(''); setHelpDesc(''); help.reload()
    } catch { setError(true) } finally { setBusy(false) }
  }
  const act = async (id: string, action: 'accept' | 'finish' | 'confirm') => {
    try { await governance.helpAction(id, action, meId); help.reload() } catch { help.reload() }
  }

  return (
    <div className="wrap">
      {tabs.length > 0 && (
        <div className="toolbar" style={{ marginBottom: 12 }}>
          <Seg value={active} onChange={v => setTab(v as typeof tab)} options={tabs.map(v => ({ v, label: t('people.tab.' + v) }))} />
        </div>)}
      {tabs.length === 0 && <Empty title={t('people.allDisabled')} />}

      {active !== 'help' && tabs.length > 0 && (
        <Panel pad={false} title={t('people.tab.' + active)}
          right={(active === 'thanks' || canRecognize) ? <GiveForm kind={active} onDone={appreciation.reload} /> : undefined}>
          {appreciation.loading && <p role="status" style={{ padding: 16 }}>{t('common.loading')}</p>}
          {appreciation.error && <p role="alert" style={{ padding: 16 }}>{t('people.error')} <button className="btn" onClick={appreciation.reload}>{t('incentives.retry')}</button></p>}
          {appreciation.data && appreciation.data.length === 0 && <Empty title={t('people.empty.' + active)} hint={t('people.emptyHint.' + active)} />}
          {appreciation.data?.map(a => {
            const from = a.senderUserId ?? a.issuerUserId
            return (
              <div className="aitem" key={a.id}>
                <Avatar name={name(from)} size={26} />
                <div style={{ flex: 1, minWidth: 0 }}>
                  <div style={{ fontSize: 13 }}>
                    <b dir="auto">{name(from)}</b> → <b dir="auto">{name(a.recipientUserId)}</b>
                  </div>
                  <div dir="auto" style={{ fontSize: 12.5, marginTop: 2 }}>{a.message}</div>
                  <div className="dim" style={{ fontSize: 11.5, marginTop: 2 }}>{ago(a.createdAt)}</div>
                </div>
              </div>
            )
          })}
        </Panel>)}

      {active === 'help' && enabled.help && (
        <Panel pad={false} title={t('people.tab.help')}
          right={<button className="btn primary" onClick={() => setHelpOpen(true)}>+ {t('people.requestHelp')}</button>}>
          {help.loading && <p role="status" style={{ padding: 16 }}>{t('common.loading')}</p>}
          {help.error && <p role="alert" style={{ padding: 16 }}>{t('people.error')} <button className="btn" onClick={help.reload}>{t('incentives.retry')}</button></p>}
          {help.data && help.data.length === 0 && <Empty title={t('people.empty.help')} hint={t('people.emptyHint.help')} />}
          {help.data?.map(h => (
            <div className="aitem" key={h.id}>
              <div style={{ flex: 1, minWidth: 0 }}>
                <div style={{ display: 'flex', gap: 8, alignItems: 'center', flexWrap: 'wrap' }}>
                  <b dir="auto">{h.title}</b>
                  <span className={'bd ' + (h.status === 'OPEN' ? 'bd-important' : h.status === 'CONFIRMED' ? 'bd-normal' : 'bd-none')}>
                    {t('people.help.status.' + h.status)}</span>
                </div>
                <div className="dim" style={{ fontSize: 12, marginTop: 4 }}>
                  {name(h.requesterUserId)} · {ago(h.createdAt)}
                  {h.acceptedByUserId && <> · {t('people.help.acceptedBy', { name: name(h.acceptedByUserId) })}</>}
                </div>
                {h.description && <div className="dim" style={{ fontSize: 12.5 }} dir="auto">{h.description}</div>}
              </div>
              {h.status === 'OPEN' && h.requesterUserId !== meId &&
                <button className="btn" disabled={busy} onClick={() => act(h.id, 'accept')}>{t('people.help.accept')}</button>}
              {h.status === 'ACCEPTED' && h.acceptedByUserId === meId &&
                <button className="btn" disabled={busy} onClick={() => act(h.id, 'finish')}>{t('people.help.finish')}</button>}
              {h.status === 'FINISHED' && h.requesterUserId === meId &&
                <button className="btn primary" disabled={busy} onClick={() => act(h.id, 'confirm')}>{t('people.help.confirm')}</button>}
            </div>
          ))}
          <Modal open={helpOpen} onClose={() => setHelpOpen(false)} title={t('people.requestHelp')}>
            {error && <p role="alert">{t('people.error')}</p>}
            <Field label={t('common.title')}>
              <input value={helpTitle} maxLength={200} onChange={e => setHelpTitle(e.target.value)} autoFocus />
            </Field>
            <Field label={t('common.description')}>
              <textarea dir={helpDesc ? 'auto' : undefined} value={helpDesc} maxLength={1000}
                onChange={e => setHelpDesc(e.target.value)} />
            </Field>
            <div className="actionbar" style={{ position: 'static', margin: '4px -18px -18px' }}>
              <button className="btn" onClick={() => setHelpOpen(false)}>{t('common.cancel')}</button>
              <button className="btn primary" disabled={busy || !helpTitle.trim() || !helpDesc.trim()} onClick={submitHelp}>
                {t('people.send')}</button>
            </div>
          </Modal>
        </Panel>)}
    </div>
  )
}

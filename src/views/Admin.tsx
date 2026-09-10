import { useState } from 'react'
import { useStore, useMe } from '../store'
import { MAX_ACTIVE, activeCount, balanceOf } from '../domain/engine'
import { Avatar, Coin, Drawer, Field, LedgerBadge, Modal, Panel, ago, coins, roleKey } from '../ui'
import { useI18n } from '../i18n'

/* Per-person operational view: workload, contribution mix and the wallet
   entries behind the balance — one click from the People table. */
function PersonDrawer({ userId, onClose }: { userId: string | null; onClose: () => void }) {
  const { state } = useStore()
  const { t } = useI18n()
  const u = state.users.find(x => x.id === userId)
  if (!u) return <Drawer open={!!userId} onClose={onClose} title={t('common.person')}>—</Drawer>
  const mine = state.ledger.filter(l => l.userId === u.id)
  const earned = mine.filter(l => (l.type === 'TASK_REWARD' || l.type === 'TASK_PARTIAL_REWARD') && l.amount > 0)
    .reduce((a, l) => a + l.amount, 0)
  const spent = mine.filter(l => l.type === 'REDEMPTION').reduce((a, l) => a + Math.abs(l.amount), 0)
  const deducted = mine.filter(l => l.amount < 0 && l.type !== 'REDEMPTION').reduce((a, l) => a + Math.abs(l.amount), 0)
  const myContribs = state.tasks.flatMap(t => t.contributions.map(c => ({ ...c, taskTitle: t.title })))
    .filter(c => c.employeeId === u.id)
  const waiting = state.tasks.filter(t => t.ownerId === u.id && t.status === 'SUBMITTED')
  const active = activeCount(state, u.id)
  return (
    <Drawer open onClose={onClose} title={<><span dir="auto">{u.name}</span><small><span dir="auto">{u.position}</span> · {t(roleKey(u.role))}</small></>}>
      <div className="dsec">
        <div style={{ display: 'flex', gap: 8, alignItems: 'center', marginBottom: 12 }}>
          <Avatar name={u.name} size={34} />
          <div>
            <b dir="auto">{u.name}</b>
            <div className="dim" style={{ fontSize: 12 }} dir="auto">{u.position}</div>
          </div>
          <div style={{ flex: 1 }} />
          <Coin n={balanceOf(state, u.id)} />
        </div>
        <dl className="kv">
          <dt>{t('admin.activeWork')}</dt><dd className="num">{t(active === 1 ? 'admin.activeTasksOne' : 'admin.activeTasksMany', { active, max: MAX_ACTIVE })}</dd>
          <dt>{t('admin.waitingReview')}</dt><dd className="num">{t(waiting.length === 1 ? 'admin.submissionsOne' : 'admin.submissionsMany', { count: waiting.length })}</dd>
          <dt>{t('admin.completedContrib')}</dt><dd className="num">{myContribs.filter(c => c.decision === 'APPROVED').length}</dd>
          <dt>{t('admin.partialContrib')}</dt><dd className="num">{myContribs.filter(c => c.decision !== 'APPROVED').length} <span className="faint" style={{ fontSize: 11 }}>{t('admin.partialContribHint')}</span></dd>
          <dt>{t('admin.totalEarned')}</dt><dd><Coin n={earned} /></dd>
          <dt>{t('admin.spentInShop')}</dt><dd><Coin n={spent} /></dd>
          <dt>{t('admin.deducted')}</dt><dd><Coin n={deducted} /> <span className="faint" style={{ fontSize: 11 }}>{t('admin.deductedHint')}</span></dd>
        </dl>
      </div>
      <div className="dsec">
        <span className="eyebrow">{t('admin.recentWalletEntries')}</span>
        {mine.length === 0
          ? <div className="faint" style={{ fontSize: 12.5, marginTop: 8 }}>{t('admin.noLedgerEntries')}</div>
          : <div className="tline" style={{ marginTop: 10 }}>
              {[...mine].sort((a, b) => b.at - a.at).slice(0, 10).map(l => (
                <div className="tl-item" key={l.id}>
                  <div className="head">
                    <LedgerBadge t={l.type} />
                    <Coin n={l.amount} sign />
                  </div>
                  <div className="why" dir="auto">{l.ref}</div>
                  <div className="when">{ago(l.at)}</div>
                </div>
              ))}
            </div>}
      </div>
    </Drawer>
  )
}

/* Company-level upload policy editor (§18). */
function UploadPolicyForm() {
  const { state, dispatch } = useStore()
  const me = useMe()
  const { t } = useI18n()
  const [perFile, setPerFile] = useState(String(state.settings.maxFileSizeMb))
  const [total, setTotal] = useState(String(state.settings.maxSubmissionTotalMb))
  const dirty = +perFile !== state.settings.maxFileSizeMb || +total !== state.settings.maxSubmissionTotalMb
  return (
    <div style={{ display: 'flex', gap: 12, alignItems: 'flex-end', flexWrap: 'wrap' }}>
      <Field label={t('admin.maxFileSize')}>
        <input type="number" min={1} max={100} value={perFile} onChange={e => setPerFile(e.target.value)} style={{ width: 130 }} />
      </Field>
      <Field label={t('admin.maxSubmissionTotal')}>
        <input type="number" min={1} max={500} value={total} onChange={e => setTotal(e.target.value)} style={{ width: 130 }} />
      </Field>
      <button className="btn primary" disabled={!dirty || !(+perFile > 0) || !(+total > 0)}
        style={{ marginBottom: 13 }}
        onClick={() => dispatch({
          type: 'UPDATE_SETTINGS', by: me.id,
          settings: { maxFileSizeMb: +perFile, maxSubmissionTotalMb: +total },
        })}>{t('admin.action.savePolicy')}</button>
    </div>
  )
}

export function AdminView() {
  const { state, dispatch, reset } = useStore()
  const me = useMe()
  const { t } = useI18n()
  const [adjustFor, setAdjustFor] = useState<string | null>(null)
  const [amount, setAmount] = useState('')
  const [reason, setReason] = useState('')
  const [personFor, setPersonFor] = useState<string | null>(null)

  return (
    <div className="wrap">
      <Panel pad={false} title={t('admin.peopleWallets')} right={<span className="eyebrow" dir="auto">{state.company}</span>}>
        <div className="table-wrap">
          <table>
            <thead><tr><th>{t('common.person')}</th><th>{t('admin.systemRole')}</th><th>{t('common.position')}</th><th>{t('admin.fulfillment')}</th><th className="n">{t('common.balance')}</th><th className="n"></th></tr></thead>
            <tbody>
              {state.users.map(u => {
                const admin = u.role === 'ADMIN'
                return (
                <tr key={u.id} style={{ cursor: 'pointer' }} onClick={() => setPersonFor(u.id)}
                  title={t('admin.openOperational')}>
                  <td><span style={{ display: 'inline-flex', alignItems: 'center', gap: 8 }}>
                    <Avatar name={u.name} size={22} /><b dir="auto">{u.name}</b></span></td>
                  <td><span className="bd bd-normal">{t(roleKey(u.role))}</span></td>
                  <td className="dim" dir="auto">{u.position}</td>
                  {/* N2.2 §6: REWARD_FULFILL is a capability, separate from
                      the system Role — admin-granted to employees/managers,
                      it unlocks nothing but executor seats on rewards.
                      Admins fulfill by office and never carry the flag. */}
                  <td onClick={e => e.stopPropagation()}>
                    {admin ? <span className="dim" style={{ fontSize: 11.5 }}>{t('admin.byOffice')}</span> : (
                      <button className="btn" style={{ fontSize: 11.5, padding: '3px 10px' }}
                        aria-label={t('admin.fulfillToggleAria', { name: u.name })}
                        onClick={() => dispatch({ type: 'TOGGLE_FULFILL_PERMISSION', by: me.id, userId: u.id })}>
                        {u.canFulfillRewards ? t('admin.grantedRevoke') : t('admin.grant')}
                      </button>
                    )}
                  </td>
                  {/* Admins manage the economy but do not participate in it —
                      no spendable wallet, no Adjust action (M1-C A1). */}
                  <td className="n">{admin ? <span className="dim" style={{ fontSize: 11.5 }}>— n/a</span> : <Coin n={balanceOf(state, u.id)} />}</td>
                  <td className="n">
                    {!admin && (
                      <button className="btn" style={{ fontSize: 11.5, padding: '3px 10px' }}
                        onClick={e => { e.stopPropagation(); setAdjustFor(u.id); setAmount(''); setReason('') }}>{t('admin.action.adjust')}</button>
                    )}
                  </td>
                </tr>
                )
              })}
            </tbody>
          </table>
        </div>
      </Panel>

      <Panel title={t('admin.uploadPolicy')}>
        <p className="dim" style={{ fontSize: 12.5, marginBottom: 12 }}>
          {t('admin.uploadPolicyNote')}
        </p>
        <UploadPolicyForm />
      </Panel>

      <Panel title={t('admin.demoControls')}>
        <p className="dim" style={{ fontSize: 12.5, marginBottom: 12 }}>
          {t('admin.demoStorageNote')}
        </p>
        <button className="btn" onClick={() => {
          if (confirm(t('admin.resetConfirm'))) reset()
        }}>{t('admin.action.resetDemo')}</button>
      </Panel>

      <PersonDrawer userId={personFor} onClose={() => setPersonFor(null)} />

      <Modal open={!!adjustFor} onClose={() => setAdjustFor(null)}
        title={<>{t('admin.adjustmentTitle')}<small>{t('admin.adjustmentSub', { name: state.users.find(u => u.id === adjustFor)?.name ?? '' })}</small></>}>
        <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 12 }}>
          <Field label={t('admin.amountLabel')}>
            <input type="number" value={amount} onChange={e => setAmount(e.target.value)} placeholder={t('admin.amountPlaceholder')} autoFocus />
          </Field>
          <Field label={t('wallet.currentBalance')}>
            <input dir="auto" type="text" disabled value={coins(balanceOf(state, adjustFor ?? ''))} />
          </Field>
        </div>
        <Field label={t('admin.reasonRequired')}>
          <textarea dir={reason ? 'auto' : undefined} value={reason} onChange={e => setReason(e.target.value)}
            placeholder={t('admin.reasonPlaceholder')} />
        </Field>
        <div className="actionbar" style={{ position: 'static', margin: '4px -18px -18px' }}>
          <button className="btn" onClick={() => setAdjustFor(null)}>{t('common.cancel')}</button>
          <button className="btn primary" disabled={!reason.trim() || !+amount} onClick={() => {
            dispatch({ type: 'ADMIN_ADJUST', by: me.id, userId: adjustFor!, amount: +amount, reason: reason.trim() })
            setAdjustFor(null)
          }}>{t('admin.action.postAdjustment')}</button>
        </div>
      </Modal>
    </div>
  )
}

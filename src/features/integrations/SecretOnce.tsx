/* WS5 — one-time secret presentation + rotation confirmation, shared by all
 * three integration providers.
 *
 * Contract (mirrors the backend): a signing secret is returned exactly once,
 * in the create/rotate response. It is held only in component state — never
 * in browser persistence, URLs, analytics or listings. Reloading the page or
 * dismissing this card means it is gone; the only recovery is rotation. */
import { useState } from 'react'
import { Modal } from '../../ui'
import { useI18n } from '../../i18n'

export function SecretOnce({ secret, onDismiss }: { secret: string; onDismiss: () => void }) {
  const { t } = useI18n()
  const [copied, setCopied] = useState(false)
  const copy = async () => {
    try {
      await navigator.clipboard.writeText(secret)
      setCopied(true)
    } catch { /* clipboard unavailable — the admin can still select the text */ }
  }
  return (
    <div className="panel" role="status" data-testid="secret-once"
      style={{ padding: '11px 14px', marginBlock: 10, borderInlineStart: '3px solid var(--accent, var(--pos))' }}>
      <b style={{ fontSize: 12.5 }}>{t('integrations.secretTitle')}</b>
      <p className="dim" style={{ fontSize: 12, marginBlock: 6 }}>{t('integrations.secretBody')}</p>
      <div style={{ display: 'flex', gap: 8, alignItems: 'center', flexWrap: 'wrap' }}>
        <code dir="ltr" style={{ userSelect: 'all', fontSize: 12.5 }}>{secret}</code>
        <button className="btn" onClick={copy}>{t(copied ? 'integrations.action.copied' : 'integrations.action.copy')}</button>
        <button className="btn primary" onClick={onDismiss}>{t('integrations.action.dismiss')}</button>
      </div>
    </div>
  )
}

/* Rotation invalidates the current secret immediately (no overlap) — the
 * confirmation states the impact BEFORE the irreversible action. */
export function RotateConfirm({ open, busy, onCancel, onConfirm }: {
  open: boolean; busy: boolean; onCancel: () => void; onConfirm: () => void
}) {
  const { t } = useI18n()
  return (
    <Modal open={open} onClose={onCancel} title={t('integrations.rotateTitle')}>
      <p style={{ fontSize: 13, lineHeight: 1.6 }}>{t('integrations.rotateBody')}</p>
      <div className="actionbar" style={{ position: 'static', margin: '4px -18px -18px' }}>
        <button className="btn" onClick={onCancel}>{t('common.cancel')}</button>
        <button className="btn primary" disabled={busy} onClick={onConfirm}>
          {t('integrations.rotateConfirm')}</button>
      </div>
    </Modal>
  )
}

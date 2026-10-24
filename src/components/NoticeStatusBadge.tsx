import type { Notice, State } from '../domain/model'
import { noticeActionState } from '../domain/noticeStatus'
import { NotifBadge } from '../ui'
import { useI18n } from '../i18n'

export function NoticeStatusBadge({ state, notice }: { state: State; notice: Notice }) {
  const { t } = useI18n()
  const status = noticeActionState(state, notice)
  return status === 'CURRENT' ? <NotifBadge l={notice.level} />
    : <span className="bd bd-none">{t(status === 'HISTORICAL'
      ? 'notification.historical' : 'notification.statusUnknown')}</span>
}

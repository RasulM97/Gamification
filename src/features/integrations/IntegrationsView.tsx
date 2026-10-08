/* Integrations view (WS5) — thin composer over the per-provider sections.
 * Separates Capability (module on/off, company-scoped, managed under Product
 * configuration) from Connection (a bound external source/workspace) and
 * Credential (the one-time signing secret). A disabled capability locks
 * management actions but never hides existing connections or credentials.
 * The generic webhook intake has no capability flag and is always available.
 * Admin-only (the backend enforces it; the nav gates it). */
import { useStore } from '../../store'
import { useI18n } from '../../i18n'
import { IS_DEMO } from '../../runtime'
import { GithubSection } from './GithubPanel'
import { SlackSection } from './SlackPanel'
import { WebhookSection } from './WebhookPanel'

export function IntegrationsView() {
  const { state } = useStore()
  const { t } = useI18n()
  /* Mirrors App.tsx capability reads: enabled only when explicitly true
     (demo mode always enabled). Listings stay visible either way. */
  const cap = (key: 'GITHUB_CONNECTOR' | 'SLACK_CONNECTOR') =>
    IS_DEMO || state.capabilities?.[key] === true
  const lockHint = t('integrations.capabilityOffNote')
  return (
    <div className="wrap">
      <GithubSection locked={!cap('GITHUB_CONNECTOR')} lockHint={lockHint} />
      <SlackSection locked={!cap('SLACK_CONNECTOR')} lockHint={lockHint} />
      <WebhookSection />
    </div>
  )
}

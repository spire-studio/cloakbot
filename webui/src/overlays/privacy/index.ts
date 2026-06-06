/**
 * CloakBot privacy overlay — the only CloakBot-authored frontend.
 *
 * Fed by the W2 backend side-channel (``agent_ui.privacy`` on ``message``
 * frames + standalone ``privacy_snapshot`` / ``privacy_trace`` / ``tool_approval``
 * frames). Everything here is additive over the adopted upstream Workbench
 * webui; nothing forks an upstream component.
 */
export { PrivacyStateProvider, usePrivacyState } from './context/PrivacyStateProvider'
export type { PrivacyHeaderStats } from './context/PrivacyStateProvider'
export { onPrivacy, classifyPrivacyFrame, extractPrivacyPayload } from './lib/privacy-client-lane'
export type { PrivacyEvent, PrivacyEventHandler, PrivacyLaneClient } from './lib/privacy-client-lane'
export { PrivacyPanel } from './components/PrivacyPanel'
export { BlockedCounter } from './components/BlockedCounter'
export { PrivacyTraceRow } from './components/PrivacyTraceRow'
export { RestorationAnnotations } from './components/RestorationAnnotations'
export { ToolApprovalPrompt, PendingToolApprovals } from './components/ToolApprovalPrompt'
export { AnnotatedMarkdown } from './lib/annotated-markdown'
export * from './types'

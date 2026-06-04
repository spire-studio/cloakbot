import { ArrowLeftRight, ChevronLeft, ChevronRight, Download, Send, Shield, Terminal } from 'lucide-react'
import type { ReactNode } from 'react'
import { useState } from 'react'

import { cn } from '@/lib/utils'
import { GhostButton, ScrollArea, Tabs, TabsContent, TabsList, TabsTrigger } from '@/overlays/privacy/lib/ui'
import { ComputationLog } from '@/overlays/privacy/components/ComputationLog'
import { EntitySummary } from '@/overlays/privacy/components/EntitySummary'
import { PromptLog } from '@/overlays/privacy/components/PromptLog'
import { buildAuditRecords, downloadAuditJsonl } from '@/overlays/privacy/lib/export-audit'
import { usePrivacyState } from '@/overlays/privacy/context/PrivacyStateProvider'

type PrivacyPanelProps = {
  open: boolean
  onToggle: () => void
  sessionId?: string
}

type PanelSectionProps = {
  title: string
  description: string
  children: ReactNode
}

const inspectorTabs = [
  { value: 'entities', label: 'Entities', icon: Shield },
  { value: 'remote-prompts', label: 'Prompts', icon: Send },
  { value: 'local-computations', label: 'Compute', icon: Terminal },
] as const

function PanelSection({ title, description, children }: PanelSectionProps) {
  return (
    <section className="space-y-3.5">
      <div>
        <div className="text-[11px] tracking-[0.08em] text-muted-foreground">{title}</div>
        <p className="mt-1 text-sm leading-[1.55] text-muted-foreground">{description}</p>
      </div>
      {children}
    </section>
  )
}

/**
 * Privacy Inspector dock — Entities / Remote-Prompts / Local-Computations.
 *
 * Reads accumulated state from :func:`usePrivacyState` (fed by the privacy
 * client lane), so App.tsx only has to mount it and toggle ``open``. Docks in
 * ``<main>`` beside the thread.
 */
export function PrivacyPanel({ open, onToggle, sessionId }: PrivacyPanelProps) {
  const { snapshot, turns, timelinesByTurnId } = usePrivacyState()
  const [activeTab, setActiveTab] = useState<(typeof inspectorTabs)[number]['value']>('entities')
  const totalComputations = turns.reduce((sum, turn) => sum + turn.localComputations.length, 0)
  const totalToolResults = turns.reduce((sum, turn) => sum + (turn.toolResults?.length ?? 0), 0)
  const highSeverityCount = snapshot.entities.filter((entity) => entity.severity === 'high').length
  const mathTurnCount = turns.filter((turn) => turn.intent === 'math').length

  const canExport = snapshot.total_entities > 0 || turns.length > 0
  const handleExportAudit = () => {
    const records = buildAuditRecords({
      sessionId: sessionId ?? 'unknown-session',
      snapshot,
      turns,
      timelinesByTurnId,
    })
    if (records.length === 0) return
    downloadAuditJsonl(records, { sessionId: sessionId ?? 'session' })
  }

  return (
    <aside
      data-testid="privacy-panel"
      className={cn(
        'shrink-0 border-t border-border bg-background backdrop-blur-xl transition-all duration-200 lg:border-l lg:border-t-0',
        open
          ? 'flex max-h-[40vh] w-full flex-col md:h-full md:max-h-none md:w-[392px]'
          : 'hidden md:flex md:h-full md:w-[60px] md:flex-col',
      )}
    >
      <div
        className={cn(
          'flex items-center justify-between gap-3 px-4 py-3.5',
          !open && 'h-full flex-col justify-start px-2 py-4',
        )}
      >
        {open ? (
          <>
            <div className="min-w-0">
              <div className="flex items-center gap-2 text-[15px] text-foreground">
                <Shield className="h-4 w-4 text-muted-foreground" />
                <span>Privacy Inspector</span>
              </div>
              <div className="mt-1 text-[12px] leading-[1.5] text-muted-foreground">
                Entities, sanitized payloads, and local math.
              </div>
            </div>
            <GhostButton onClick={onToggle} aria-label="Collapse privacy panel" className="h-8 w-8 rounded-xl">
              <ChevronRight className="h-4 w-4" />
            </GhostButton>
          </>
        ) : (
          <>
            <GhostButton onClick={onToggle} aria-label="Expand privacy panel" className="h-9 w-9 rounded-xl">
              <ChevronLeft className="h-4 w-4" />
            </GhostButton>
            <div className="text-center text-[11px] font-semibold uppercase tracking-[0.24em] text-muted-foreground [writing-mode:vertical-rl]">
              Privacy
            </div>
            <ArrowLeftRight aria-hidden className="h-0 w-0 opacity-0" />
          </>
        )}
      </div>

      {open && (
        <>
          <div className="mx-4 mb-3 rounded-2xl border border-border bg-secondary/75 p-2">
            <div className="grid grid-cols-2 gap-2">
              <Stat label="Entities" value={snapshot.total_entities} />
              <Stat label="High severity" value={highSeverityCount} />
              <Stat label="Turns" value={turns.length} />
              <Stat label="Math turns" value={mathTurnCount} />
            </div>
            <div className="mt-2 rounded-md border border-border/70 bg-card/70 px-2 py-1.5">
              <div className="grid grid-cols-2 gap-2">
                <Stat label="Local computations" value={totalComputations} bare />
                <Stat label="Tool results" value={totalToolResults} bare />
              </div>
            </div>
            <div className="mt-2 flex items-center justify-between gap-2 rounded-md border border-border/70 bg-card/70 px-2 py-1.5">
              <div className="min-w-0">
                <div className="text-[11px] text-muted-foreground">Audit trail</div>
                <div className="mt-0.5 text-[11.5px] text-muted-foreground">Types + placeholders only — no raw values.</div>
              </div>
              <GhostButton
                onClick={handleExportAudit}
                disabled={!canExport}
                aria-label="Export audit log as JSONL"
                className="border border-border"
              >
                <Download className="h-3 w-3" />
                <span>Export JSONL</span>
              </GhostButton>
            </div>
          </div>

          <Tabs value={activeTab} onValueChange={(value) => setActiveTab(value as typeof activeTab)} className="flex min-h-0 flex-1 flex-col">
            <div className="px-4 pb-3">
              <TabsList className="grid w-full grid-cols-3">
                {inspectorTabs.map((tab) => {
                  const Icon = tab.icon
                  return (
                    <TabsTrigger key={tab.value} value={tab.value}>
                      <Icon className="h-3.5 w-3.5 shrink-0" />
                      <span>{tab.label}</span>
                    </TabsTrigger>
                  )
                })}
              </TabsList>
            </div>

            <ScrollArea className="min-h-0 flex-1 px-4 pb-4">
              <TabsContent value="entities">
                <PanelSection
                  title="Privacy Entities"
                  description={
                    snapshot.total_entities > 0
                      ? `${snapshot.total_entities} entities accumulated in this chat session`
                      : 'No privacy entities detected in this chat session yet.'
                  }
                >
                  <EntitySummary snapshot={snapshot} />
                </PanelSection>
              </TabsContent>

              <TabsContent value="remote-prompts">
                <PanelSection title="Remote Prompt Log" description="Inspect the sanitized payload sent for each turn.">
                  <PromptLog turns={turns} />
                </PanelSection>
              </TabsContent>

              <TabsContent value="local-computations">
                <PanelSection
                  title="Local Computations"
                  description="On-device arithmetic finalized after remote structure returns."
                >
                  <ComputationLog turns={turns} />
                </PanelSection>
              </TabsContent>
            </ScrollArea>
          </Tabs>
        </>
      )}
    </aside>
  )
}

function Stat({ label, value, bare }: { label: string; value: number; bare?: boolean }) {
  return (
    <div className={bare ? '' : 'rounded-md border border-border/70 bg-card/70 px-2 py-1.5'}>
      <div className="text-[11px] text-muted-foreground">{label}</div>
      <div className="mt-0.5 text-sm font-semibold text-foreground">{value}</div>
    </div>
  )
}

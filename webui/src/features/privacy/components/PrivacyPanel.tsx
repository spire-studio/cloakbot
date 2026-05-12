import { ArrowLeftRight, ChevronLeft, ChevronRight, Send, Shield, Terminal } from 'lucide-react'
import type { ReactNode } from 'react'
import { useState } from 'react'

import { Button } from '@/components/ui/button'
import { ScrollArea } from '@/components/ui/scroll-area'
import { Tabs, TabsContent, TabsList, TabsTrigger } from '@/components/ui/tabs'
import { ComputationLog } from '@/features/privacy/components/ComputationLog'
import { EntitySummary } from '@/features/privacy/components/EntitySummary'
import { PromptLog } from '@/features/privacy/components/PromptLog'
import type { PrivacySnapshot, PrivacyTurn } from '@/features/privacy/types'
import { cn } from '@/lib/utils'

type PrivacyPanelProps = {
  open: boolean
  onToggle: () => void
  snapshot: PrivacySnapshot
  turns: PrivacyTurn[]
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

export function PrivacyPanel({ open, onToggle, snapshot, turns }: PrivacyPanelProps) {
  const [activeTab, setActiveTab] = useState<(typeof inspectorTabs)[number]['value']>('entities')
  const totalComputations = turns.reduce((sum, turn) => sum + turn.localComputations.length, 0)
  const totalToolResults = turns.reduce((sum, turn) => sum + (turn.toolResults?.length ?? 0), 0)
  const highSeverityCount = snapshot.entities.filter((entity) => entity.severity === 'high').length
  const mathTurnCount = turns.filter((turn) => turn.intent === 'math').length
  const activeTabIndex = Math.max(0, inspectorTabs.findIndex((tab) => tab.value === activeTab))

  return (
    <aside
      className={cn(
        'shrink-0 border-t border-border bg-background backdrop-blur-xl transition-all duration-200 lg:border-l lg:border-t-0',
        open ? 'flex max-h-[40vh] w-full flex-col md:h-full md:max-h-none md:w-[392px]' : 'hidden md:flex md:h-full md:w-[76px] md:flex-col',
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
              <div className="mt-1 text-[12px] leading-[1.5] text-muted-foreground">Dense view of entities, payloads, and local math.</div>
            </div>
            <Button
              type="button"
              variant="ghost"
              size="icon"
              className="group h-8 w-8 rounded-xl"
              onClick={onToggle}
              aria-label="Collapse privacy panel"
            >
              <span className="relative block h-4 w-4">
                <ChevronRight className="absolute inset-0 h-4 w-4 transition-opacity group-hover:opacity-0" />
                <ArrowLeftRight className="absolute inset-0 h-4 w-4 opacity-0 transition-opacity group-hover:opacity-100" />
              </span>
            </Button>
          </>
        ) : (
          <>
            <Button
              type="button"
              variant="ghost"
              size="icon"
              className="group h-9 w-9 rounded-xl"
              onClick={onToggle}
              aria-label="Expand privacy panel"
            >
              <span className="relative block h-4 w-4">
                <ChevronLeft className="absolute inset-0 h-4 w-4 transition-opacity group-hover:opacity-0" />
                <ArrowLeftRight className="absolute inset-0 h-4 w-4 opacity-0 transition-opacity group-hover:opacity-100" />
              </span>
            </Button>
            <div className="text-center text-[11px] font-semibold uppercase tracking-[0.24em] text-muted-foreground [writing-mode:vertical-rl]">
              Privacy Panel
            </div>
          </>
        )}
      </div>

      {open && (
        <>
          <div className="mx-4 mb-3 rounded-2xl border border-border bg-secondary/75 p-2 shadow-[0_4px_24px_var(--shadow-soft)]">
            <div className="grid grid-cols-2 gap-2">
              <div className="rounded-md border border-border/70 bg-card/70 px-2 py-1.5">
                <div className="text-[11px] text-muted-foreground">Entities</div>
                <div className="mt-0.5 text-sm font-semibold text-foreground">{snapshot.total_entities}</div>
              </div>
              <div className="rounded-md border border-border/70 bg-card/70 px-2 py-1.5">
                <div className="text-[11px] text-muted-foreground">High severity</div>
                <div className="mt-0.5 text-sm font-semibold text-foreground">{highSeverityCount}</div>
              </div>
              <div className="rounded-md border border-border/70 bg-card/70 px-2 py-1.5">
                <div className="text-[11px] text-muted-foreground">Turns</div>
                <div className="mt-0.5 text-sm font-semibold text-foreground">{turns.length}</div>
              </div>
              <div className="rounded-md border border-border/70 bg-card/70 px-2 py-1.5">
                <div className="text-[11px] text-muted-foreground">Math turns</div>
                <div className="mt-0.5 text-sm font-semibold text-foreground">{mathTurnCount}</div>
              </div>
            </div>
            <div className="mt-2 rounded-md border border-border/70 bg-card/70 px-2 py-1.5">
              <div className="grid grid-cols-2 gap-2">
                <div>
                  <div className="text-[11px] text-muted-foreground">Local computations</div>
                  <div className="mt-0.5 text-sm font-semibold text-foreground">{totalComputations}</div>
                </div>
                <div>
                  <div className="text-[11px] text-muted-foreground">Tool results</div>
                  <div className="mt-0.5 text-sm font-semibold text-foreground">{totalToolResults}</div>
                </div>
              </div>
            </div>
          </div>

          <Tabs value={activeTab} onValueChange={(value) => setActiveTab(value as typeof activeTab)} className="flex min-h-0 flex-1 flex-col">
            <div className="px-4 pb-3">
              <TabsList className="relative grid h-10 w-full grid-cols-3 overflow-hidden border-0 bg-surface-subtle p-1 shadow-none">
                <span
                  aria-hidden="true"
                  className="absolute left-1 top-1 bottom-1 rounded-md bg-card shadow-[0_0_0_1px_var(--surface-outline),0_6px_18px_var(--shadow-soft)] transition-transform duration-200 ease-out"
                  style={{
                    width: 'calc((100% - 0.5rem) / 3)',
                    transform: `translateX(${activeTabIndex * 100}%)`,
                  }}
                />
                {inspectorTabs.map((tab) => {
                  const Icon = tab.icon
                  return (
                    <TabsTrigger
                      key={tab.value}
                      value={tab.value}
                      className="relative z-10 h-8 border-0 bg-transparent px-1.5 shadow-none hover:border-transparent hover:bg-transparent data-[state=active]:border-transparent data-[state=active]:bg-transparent data-[state=active]:shadow-none"
                    >
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
                <PanelSection
                  title="Remote Prompt Log"
                  description="Inspect the sanitized payload sent for each turn."
                >
                  <PromptLog turns={turns} />
                </PanelSection>
              </TabsContent>

              <TabsContent value="local-computations">
                <PanelSection
                  title="Local Computations"
                  description="Timeline of on-device arithmetic finalized after remote structure returns."
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

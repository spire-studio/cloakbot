import { ArrowLeftRight, ChevronLeft, ChevronRight, Send, Shield, Terminal } from 'lucide-react'
import type { ReactNode } from 'react'

import { Button } from '@/components/ui/button'
import { ScrollArea } from '@/components/ui/scroll-area'
import { Tabs, TabsContent, TabsList, TabsTrigger } from '@/components/ui/tabs'
import { EntitySummary } from '@/features/privacy/components/EntitySummary'
import { PromptLog } from '@/features/privacy/components/PromptLog'
import { ComputationLog } from '@/features/privacy/components/ComputationLog'
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

function PanelSection({ title, description, children }: PanelSectionProps) {
  return (
    <section className="space-y-3">
      <div>
        <div className="text-[11px] font-semibold uppercase tracking-[0.18em] text-muted-foreground">{title}</div>
        <p className="mt-1 text-xs text-muted-foreground">{description}</p>
      </div>
      {children}
    </section>
  )
}

export function PrivacyPanel({ open, onToggle, snapshot, turns }: PrivacyPanelProps) {
  return (
    <aside
      className={cn(
        'shrink-0 border-t border-border/60 bg-background/70 backdrop-blur-xl transition-all duration-200 lg:border-l lg:border-t-0',
        open ? 'flex max-h-[38vh] w-full flex-col lg:max-h-none lg:w-[360px]' : 'hidden lg:flex lg:w-[76px] lg:flex-col',
      )}
    >
      <div
        className={cn(
          'flex items-center justify-between gap-3 px-4 py-4',
          !open && 'h-full flex-col justify-start px-2 py-5',
        )}
      >
        {open ? (
          <>
            <div className="min-w-0">
              <div className="flex items-center gap-2 text-sm font-semibold text-foreground">
                <Shield className="h-4 w-4 text-muted-foreground" />
                <span>Privacy Panel</span>
              </div>
            </div>
            <Button
              type="button"
              variant="ghost"
              size="icon"
              className="group h-9 w-9 rounded-full"
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
              className="group h-10 w-10 rounded-full"
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
        <ScrollArea className="min-h-0 flex-1 px-4 pb-4">
          <Tabs defaultValue="entities" className="space-y-0 pb-2">
            <TabsList className="grid h-auto w-full grid-cols-3 gap-0.5">
              <TabsTrigger value="entities" className="h-8 px-1.5">
                <Shield className="h-3.25 w-3.25 shrink-0" />
                <span>Entities</span>
              </TabsTrigger>
              <TabsTrigger value="remote-prompts" className="h-8 px-1.5">
                <Send className="h-3.25 w-3.25 shrink-0" />
                <span>Prompts</span>
              </TabsTrigger>
              <TabsTrigger value="local-computations" className="h-8 px-1.5">
                <Terminal className="h-3.25 w-3.25 shrink-0" />
                <span>Compute</span>
              </TabsTrigger>
            </TabsList>

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
                description="The sanitized content actually sent to the remote model for each turn."
              >
                <PromptLog turns={turns} />
              </PanelSection>
            </TabsContent>

            <TabsContent value="local-computations">
              <PanelSection
                title="Local Computations"
                description="On-device arithmetic executed after the remote model returned structure."
              >
                <ComputationLog turns={turns} />
              </PanelSection>
            </TabsContent>
          </Tabs>
        </ScrollArea>
      )}
    </aside>
  )
}

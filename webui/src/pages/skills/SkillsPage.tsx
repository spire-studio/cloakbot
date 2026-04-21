import { Bolt, Wrench } from 'lucide-react'

import { Button } from '@/components/ui/button'

export function SkillsPage() {
  return (
    <div className="flex min-h-0 flex-1 flex-col bg-transparent">
      <div className="flex-1 overflow-auto p-5 lg:p-6">
        <div className="mx-auto max-w-[52rem]">
          <div className="mb-8">
            <p className="text-[10px] uppercase tracking-[0.18em] text-muted-foreground">Capability index</p>
            <h1 className="mt-2 text-[2.35rem] leading-[1.1] tracking-tight">Skills</h1>
            <p className="mt-3 max-w-2xl text-[17px] leading-[1.6] text-muted-foreground">Browse the assistant capabilities available in this workspace.</p>
          </div>

          <div className="mb-5 rounded-2xl border border-border bg-card p-6 shadow-[0_4px_24px_var(--shadow-soft)]">
            <div className="flex items-center gap-3">
              <div className="flex h-11 w-11 items-center justify-center rounded-xl bg-secondary text-secondary-foreground">
                <Bolt className="h-5 w-5" />
              </div>
              <div>
                <p className="font-serif text-[1.2rem] text-foreground">Installed Skills</p>
                <p className="text-sm leading-[1.6] text-muted-foreground">
                  Surface workspace-specific skills here before expanding into richer management controls.
                </p>
              </div>
            </div>
          </div>

          <div className="rounded-2xl border border-border bg-card p-6 text-card-foreground shadow-[0_4px_24px_var(--shadow-soft)]">
            <Wrench className="mb-4 h-8 w-8 text-muted-foreground" />
            <h3 className="mb-2 text-[1.55rem]">Skill Catalog</h3>
            <p className="mb-5 text-sm leading-[1.6] text-muted-foreground">
              This placeholder keeps the navigation structure correct while the skill management UI is still being built.
            </p>
            <Button variant="outline" className="w-full">
              Review Skills
            </Button>
          </div>
        </div>
      </div>
    </div>
  )
}

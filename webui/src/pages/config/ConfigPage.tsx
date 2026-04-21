import { Settings, Terminal } from 'lucide-react'

import { Button } from '@/components/ui/button'

export function ConfigPage() {
  return (
    <div className="flex min-h-0 flex-1 flex-col bg-transparent">
      <div className="flex-1 overflow-auto p-5 lg:p-6">
        <div className="mx-auto max-w-[52rem]">
          <div className="mb-8">
            <p className="text-[10px] uppercase tracking-[0.18em] text-muted-foreground">Workspace controls</p>
            <h1 className="mt-2 text-[2.35rem] leading-[1.1] tracking-tight">Configuration</h1>
            <p className="mt-3 max-w-2xl text-[17px] leading-[1.6] text-muted-foreground">Manage your workspace settings and preferences.</p>
          </div>

          <div className="mb-5 rounded-2xl border border-border bg-card p-6 shadow-[0_4px_24px_var(--shadow-soft)]">
            <div className="flex items-center gap-3">
              <div className="flex h-11 w-11 items-center justify-center rounded-xl bg-secondary text-secondary-foreground">
                <Terminal className="h-5 w-5" />
              </div>
              <div>
                <p className="font-serif text-[1.2rem] text-foreground">Workspace Profile</p>
                <p className="text-sm leading-[1.6] text-muted-foreground">
                  Use this area to manage runtime defaults before adding advanced controls.
                </p>
              </div>
            </div>
          </div>

          <div className="grid gap-5 md:grid-cols-2">
            <div className="rounded-2xl border border-border bg-card p-6 text-card-foreground shadow-[0_4px_24px_var(--shadow-soft)]">
              <Settings className="mb-4 h-8 w-8 text-muted-foreground" />
              <h3 className="mb-2 text-[1.55rem]">General Settings</h3>
              <p className="mb-5 text-sm leading-[1.6] text-muted-foreground">
                Configure basic options for your agent, including timeouts and memory limits.
              </p>
              <Button variant="outline" className="w-full">
                Configure
              </Button>
            </div>

            <div className="rounded-2xl border border-border bg-card p-6 text-card-foreground shadow-[0_4px_24px_var(--shadow-soft)]">
              <Terminal className="mb-4 h-8 w-8 text-muted-foreground" />
              <h3 className="mb-2 text-[1.55rem]">Tools & Plugins</h3>
              <p className="mb-5 text-sm leading-[1.6] text-muted-foreground">
                Manage the tools and plugins available to the agent during execution.
              </p>
              <Button variant="outline" className="w-full">
                Manage Tools
              </Button>
            </div>
          </div>
        </div>
      </div>
    </div>
  )
}

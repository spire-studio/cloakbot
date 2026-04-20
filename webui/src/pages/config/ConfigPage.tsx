import { Settings, Terminal } from 'lucide-react'

import { Button } from '@/components/ui/button'

export function ConfigPage() {
  return (
    <div className="flex min-h-0 flex-1 flex-col bg-transparent">
      <div className="flex-1 overflow-auto p-6 lg:p-8">
        <div className="mx-auto max-w-4xl">
          <div className="mb-8">
            <h1 className="text-3xl font-bold tracking-tight">Configuration</h1>
            <p className="mt-2 text-muted-foreground">Manage your workspace settings and preferences.</p>
          </div>

          <div className="mb-6 rounded-3xl border border-border/70 bg-card/85 p-6 shadow-sm">
            <div className="flex items-center gap-3">
              <div className="flex h-11 w-11 items-center justify-center rounded-2xl bg-secondary text-secondary-foreground">
                <Terminal className="h-5 w-5" />
              </div>
              <div>
                <p className="text-sm font-medium text-foreground">Workspace Profile</p>
                <p className="text-sm text-muted-foreground">
                  Use this area to manage runtime defaults before adding advanced controls.
                </p>
              </div>
            </div>
          </div>

          <div className="grid gap-6 md:grid-cols-2">
            <div className="rounded-3xl border bg-card/85 p-6 text-card-foreground shadow-sm">
              <Settings className="mb-4 h-8 w-8 text-muted-foreground" />
              <h3 className="mb-2 text-lg font-semibold">General Settings</h3>
              <p className="mb-4 text-sm text-muted-foreground">
                Configure basic options for your agent, including timeouts and memory limits.
              </p>
              <Button variant="outline" className="w-full">
                Configure
              </Button>
            </div>

            <div className="rounded-3xl border bg-card/85 p-6 text-card-foreground shadow-sm">
              <Terminal className="mb-4 h-8 w-8 text-muted-foreground" />
              <h3 className="mb-2 text-lg font-semibold">Tools & Plugins</h3>
              <p className="mb-4 text-sm text-muted-foreground">
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

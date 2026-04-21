import { PanelLeft } from 'lucide-react'

import { Button } from '@/components/ui/button'

import { chatViewItem, navigationItems, type WorkspaceViewId } from '../navigation.config'
import { ThemeSwitch } from './ThemeSwitch'

type ShellHeaderProps = {
  currentView: WorkspaceViewId
  onOpenNavigation: () => void
}

export function ShellHeader({ currentView, onOpenNavigation }: ShellHeaderProps) {
  const activeItem =
    currentView === 'chat'
      ? chatViewItem
      : navigationItems.find((item) => item.id === currentView) ?? navigationItems[0]
  const ActiveIcon = activeItem.icon

  return (
    <header className="border-b border-border bg-background/90 px-4 py-4 backdrop-blur-xl md:px-6">
      <div className="flex items-center justify-between gap-3">
        <div className="flex min-w-0 items-center gap-3">
          <Button
            variant="outline"
            size="icon"
            className="shrink-0 rounded-lg bg-card md:hidden"
            onClick={onOpenNavigation}
          >
            <PanelLeft className="size-4" />
          </Button>
          <div className="min-w-0 flex items-center gap-2.5">
            <ActiveIcon className="h-4 w-4 shrink-0 text-muted-foreground" />
            <h1 className="truncate text-lg text-foreground md:text-[1.35rem]">{activeItem.name}</h1>
          </div>
        </div>
        <ThemeSwitch />
      </div>
    </header>
  )
}

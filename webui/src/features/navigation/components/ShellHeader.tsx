import { PanelLeft } from 'lucide-react'

import { Button } from '@/components/ui/button'

import { navigationItems, type NavigationTabId } from '../navigation.config'

type ShellHeaderProps = {
  currentTab: NavigationTabId
  onOpenNavigation: () => void
}

export function ShellHeader({ currentTab, onOpenNavigation }: ShellHeaderProps) {
  const activeItem = navigationItems.find((item) => item.id === currentTab) ?? navigationItems[0]
  const ActiveIcon = activeItem.icon

  return (
    <header className="border-b border-border/60 bg-background/82 px-4 py-4 backdrop-blur-xl md:px-6">
      <div className="flex items-center gap-3">
        <Button
          variant="outline"
          size="icon"
          className="shrink-0 rounded-2xl border-border/70 bg-card shadow-sm md:hidden"
          onClick={onOpenNavigation}
        >
          <PanelLeft className="size-4" />
        </Button>
        <div className="min-w-0 flex items-center gap-2">
          <ActiveIcon className="h-4 w-4 shrink-0 text-muted-foreground" />
          <h1 className="truncate text-base font-semibold text-foreground">{activeItem.name}</h1>
        </div>
      </div>
    </header>
  )
}

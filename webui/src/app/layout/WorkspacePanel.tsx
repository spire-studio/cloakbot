import type { ReactNode } from 'react'

import { ShellHeader } from '@/features/navigation/components/ShellHeader'
import type { NavigationTabId } from '@/features/navigation/navigation.config'
import { cn } from '@/lib/utils'
import { WORKSPACE_BACKGROUND } from '@/shared/constants/brand'

type WorkspacePanelProps = {
  currentTab: NavigationTabId
  onOpenNavigation: () => void
  className?: string
  children: ReactNode
}

export function WorkspacePanel({
  currentTab,
  onOpenNavigation,
  className,
  children,
}: WorkspacePanelProps) {
  return (
    <div
      className={cn('flex min-h-svh min-w-0 flex-1 flex-col overflow-hidden bg-background/88', className)}
      style={WORKSPACE_BACKGROUND}
    >
      <ShellHeader currentTab={currentTab} onOpenNavigation={onOpenNavigation} />
      <main className="flex min-h-0 flex-1 flex-col overflow-hidden">{children}</main>
    </div>
  )
}

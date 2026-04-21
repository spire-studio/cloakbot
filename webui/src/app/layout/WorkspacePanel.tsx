import type { ReactNode } from 'react'

import { ShellHeader } from '@/features/navigation/components/ShellHeader'
import type { WorkspaceViewId } from '@/features/navigation/navigation.config'
import { cn } from '@/lib/utils'

type WorkspacePanelProps = {
  currentView: WorkspaceViewId
  onOpenNavigation: () => void
  className?: string
  children: ReactNode
}

export function WorkspacePanel({
  currentView,
  onOpenNavigation,
  className,
  children,
}: WorkspacePanelProps) {
  return (
    <div className={cn('flex h-full min-h-0 min-w-0 flex-1 flex-col overflow-hidden bg-background', className)}>
      <ShellHeader currentView={currentView} onOpenNavigation={onOpenNavigation} />
      <main className="flex min-h-0 flex-1 flex-col overflow-hidden">{children}</main>
    </div>
  )
}

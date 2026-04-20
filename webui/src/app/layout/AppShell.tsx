import { useState } from 'react'
import type { ReactNode } from 'react'

import { Sheet, SheetContent } from '@/components/ui/sheet'
import { NavigationPanel } from '@/features/navigation/components/NavigationPanel'
import type { NavigationTabId } from '@/features/navigation/navigation.config'
import { WORKSPACE_BACKGROUND } from '@/shared/constants/brand'

import { WorkspacePanel } from './WorkspacePanel'

type AppShellProps = {
  tabContent: Record<NavigationTabId, ReactNode>
}

export function AppShell({ tabContent }: AppShellProps) {
  const [currentTab, setCurrentTab] = useState<NavigationTabId>('chat')
  const [mobileNavigationOpen, setMobileNavigationOpen] = useState(false)
  const [desktopSidebarCollapsed, setDesktopSidebarCollapsed] = useState(false)

  const handleTabChange = (id: NavigationTabId) => {
    setCurrentTab(id)
    setMobileNavigationOpen(false)
  }

  const content = tabContent[currentTab]

  return (
    <div className="min-h-svh bg-background" style={WORKSPACE_BACKGROUND}>
      <div className="min-h-svh md:min-h-0 md:p-3">
        <div className="hidden min-h-[calc(100svh-1.5rem)] overflow-hidden rounded-[30px] border border-border/60 shadow-[0_24px_80px_rgba(61,57,41,0.12)] md:flex">
          <aside
            className={
              desktopSidebarCollapsed
                ? 'w-[88px] shrink-0 border-r border-sidebar-border/70 bg-sidebar/92 transition-[width] duration-200'
                : 'w-[240px] shrink-0 border-r border-sidebar-border/70 bg-sidebar/92 transition-[width] duration-200'
            }
          >
            <NavigationPanel
              currentTab={currentTab}
              setCurrentTab={handleTabChange}
              onToggleSidebar={() => setDesktopSidebarCollapsed((prev) => !prev)}
              collapsed={desktopSidebarCollapsed}
            />
          </aside>
          <WorkspacePanel
            currentTab={currentTab}
            onOpenNavigation={() => setMobileNavigationOpen(true)}
            className="min-h-[calc(100svh-1.5rem)]"
          >
            {content}
          </WorkspacePanel>
        </div>

        <WorkspacePanel
          currentTab={currentTab}
          onOpenNavigation={() => setMobileNavigationOpen(true)}
          className="md:hidden"
        >
          {content}
        </WorkspacePanel>
      </div>

      <Sheet open={mobileNavigationOpen} onOpenChange={setMobileNavigationOpen}>
        <SheetContent side="left" className="w-[290px] border-r border-sidebar-border bg-sidebar p-0 sm:max-w-[290px]">
          <NavigationPanel currentTab={currentTab} setCurrentTab={handleTabChange} />
        </SheetContent>
      </Sheet>
    </div>
  )
}

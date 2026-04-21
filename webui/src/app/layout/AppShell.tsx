import { cloneElement, isValidElement, useState } from 'react'
import type { ReactElement, ReactNode } from 'react'

import { Sheet, SheetContent } from '@/components/ui/sheet'
import { NavigationPanel } from '@/features/navigation/components/NavigationPanel'
import type { NavigationTabId, WorkspaceViewId } from '@/features/navigation/navigation.config'

import { WorkspacePanel } from './WorkspacePanel'

type AppShellProps = {
  tabContent: {
    chat: ReactNode
    config: ReactNode
    skills?: ReactNode
  }
}

type ChatNavigationState = {
  sessions: Array<{ id: string; title: string }>
  activeSessionId: string
  onSelectSession: (id: string) => void
  onStartNewSession: () => void
}

const defaultChatNavigation: ChatNavigationState = {
  sessions: [{ id: 'default', title: 'New chat' }],
  activeSessionId: 'default',
  onSelectSession: () => {},
  onStartNewSession: () => {},
}

export function AppShell({ tabContent }: AppShellProps) {
  const [currentView, setCurrentView] = useState<WorkspaceViewId>('chat')
  const [mobileNavigationOpen, setMobileNavigationOpen] = useState(false)
  const [desktopSidebarCollapsed, setDesktopSidebarCollapsed] = useState(false)
  const [chatNavigation, setChatNavigation] = useState<ChatNavigationState>(defaultChatNavigation)

  const handleGlobalViewChange = (id: NavigationTabId) => {
    setCurrentView(id)
    setMobileNavigationOpen(false)
  }

  const chatNode = tabContent.chat
  const chatContent =
    isValidElement(chatNode) && chatNode.type
      ? cloneElement(chatNode as ReactElement<{ onSessionNavigationChange?: (state: ChatNavigationState) => void }>, {
          onSessionNavigationChange: setChatNavigation,
        })
      : chatNode

  const content =
    currentView === 'chat'
      ? chatContent
      : currentView === 'skills'
        ? (tabContent.skills ?? tabContent.config)
        : tabContent.config

  return (
    <div className="h-svh overflow-hidden bg-background">
      <div className="h-svh">
        <div className="hidden h-full overflow-hidden md:flex">
          <aside
            aria-label="Session Rail"
            className={
              desktopSidebarCollapsed
                ? 'w-[80px] shrink-0 border-r border-sidebar-border bg-sidebar/96 transition-[width] duration-200'
                : 'w-[272px] shrink-0 border-r border-sidebar-border bg-sidebar/96 transition-[width] duration-200'
            }
          >
            <NavigationPanel
              sessions={chatNavigation.sessions}
              activeSessionId={chatNavigation.activeSessionId}
              currentView={currentView}
              onSelectGlobalView={handleGlobalViewChange}
              onSelectSession={(id) => {
                setCurrentView('chat')
                chatNavigation.onSelectSession(id)
              }}
              onStartNewSession={() => {
                setCurrentView('chat')
                chatNavigation.onStartNewSession()
              }}
              onToggleSidebar={() => setDesktopSidebarCollapsed((prev) => !prev)}
              collapsed={desktopSidebarCollapsed}
            />
          </aside>
          <WorkspacePanel
            currentView={currentView}
            onOpenNavigation={() => setMobileNavigationOpen(true)}
            className="h-full"
          >
            {content}
          </WorkspacePanel>
        </div>

        <WorkspacePanel
          currentView={currentView}
          onOpenNavigation={() => setMobileNavigationOpen(true)}
          className="md:hidden"
        >
          {content}
        </WorkspacePanel>
      </div>

      <Sheet open={mobileNavigationOpen} onOpenChange={setMobileNavigationOpen}>
        <SheetContent side="left" className="w-[292px] border-r border-sidebar-border bg-sidebar p-0 sm:max-w-[292px]">
          <NavigationPanel
            sessions={chatNavigation.sessions}
            activeSessionId={chatNavigation.activeSessionId}
            currentView={currentView}
            onSelectGlobalView={handleGlobalViewChange}
            onSelectSession={(id) => {
              setCurrentView('chat')
              chatNavigation.onSelectSession(id)
              setMobileNavigationOpen(false)
            }}
            onStartNewSession={() => {
              setCurrentView('chat')
              chatNavigation.onStartNewSession()
              setMobileNavigationOpen(false)
            }}
          />
        </SheetContent>
      </Sheet>
    </div>
  )
}

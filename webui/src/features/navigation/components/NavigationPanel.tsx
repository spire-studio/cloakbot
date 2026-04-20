import { PanelLeft } from 'lucide-react'

import { Button } from '@/components/ui/button'
import { cn } from '@/lib/utils'
import { BRAND_LOGO_PATH, BRAND_NAME } from '@/shared/constants/brand'

import { navigationItems, type NavigationTabId } from '../navigation.config'

type NavigationPanelProps = {
  currentTab: NavigationTabId
  setCurrentTab: (id: NavigationTabId) => void
  onToggleSidebar?: () => void
  collapsed?: boolean
}

export function NavigationPanel({
  currentTab,
  setCurrentTab,
  onToggleSidebar,
  collapsed = false,
}: NavigationPanelProps) {
  return (
    <div className="flex h-full flex-col">
      <div className="px-3 pt-3">
        <div className={cn('flex items-center gap-3', collapsed && 'justify-center')}>
          {!collapsed && (
            <>
              <img src={BRAND_LOGO_PATH} alt="Cloakbot logo" className="h-11 w-11 shrink-0 object-contain" />
              <p className="min-w-0 flex-1 truncate text-xl font-bold text-foreground">{BRAND_NAME}</p>
            </>
          )}
          {onToggleSidebar && (
            <Button
              variant="ghost"
              size="icon"
              className={cn(
                'shrink-0 cursor-ew-resize bg-transparent text-sidebar-foreground hover:bg-sidebar-accent hover:text-sidebar-accent-foreground',
                collapsed ? 'h-10 w-full rounded-2xl px-0' : 'h-9 w-9 rounded-2xl'
              )}
              onClick={onToggleSidebar}
              aria-label={collapsed ? 'Expand sidebar' : 'Collapse sidebar'}
              title={collapsed ? 'Expand sidebar' : 'Collapse sidebar'}
            >
              <PanelLeft className="size-4" />
            </Button>
          )}
        </div>
      </div>

      <nav className="px-3 pt-4">
        <div className="space-y-2">
          {navigationItems.map((item) => {
            const isActive = currentTab === item.id
            return (
              <button
                key={item.id}
                type="button"
                onClick={() => setCurrentTab(item.id)}
                title={item.name}
                aria-label={item.name}
                className={cn(
                  'flex w-full items-center gap-3 rounded-2xl px-3 py-2.5 text-left text-[13px] transition-colors',
                  collapsed && 'justify-center px-0',
                  isActive
                    ? 'bg-sidebar-accent text-sidebar-accent-foreground shadow-sm'
                    : 'text-sidebar-foreground/78 hover:bg-sidebar-accent/65 hover:text-sidebar-accent-foreground'
                )}
              >
                <item.icon className="size-4 shrink-0" />
                {!collapsed && (
                  <div className="min-w-0">
                    <div className="font-medium">{item.name}</div>
                  </div>
                )}
              </button>
            )
          })}
        </div>
      </nav>
    </div>
  )
}

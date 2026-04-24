import { useEffect, useState } from 'react'

import { PanelLeft, Plus } from 'lucide-react'

import { Button } from '@/components/ui/button'
import { navigationItems, type NavigationTabId } from '@/features/navigation/navigation.config'
import { cn } from '@/lib/utils'
import { BRAND_LOGO_PATH, BRAND_NAME } from '@/shared/constants/brand'

type NavigationSession = {
  id: string
  title: string
}

type NavigationPanelProps = {
  sessions: NavigationSession[]
  activeSessionId: string
  currentView: 'chat' | NavigationTabId
  onSelectGlobalView: (id: NavigationTabId) => void
  onSelectSession: (id: string) => void
  onStartNewSession: () => void
  onToggleSidebar?: () => void
  collapsed?: boolean
}

type GatewayConnectionState = 'checking' | 'connected' | 'disconnected'

export function NavigationPanel({
  sessions,
  activeSessionId,
  currentView,
  onSelectGlobalView,
  onSelectSession,
  onStartNewSession,
  onToggleSidebar,
  collapsed = false,
}: NavigationPanelProps) {
  const sectionPaddingClass = collapsed ? 'px-2' : 'px-3'

  return (
    <div className="flex h-full flex-col">
      <div className={cn(sectionPaddingClass, 'pt-3')}>
        <div className={cn('flex items-center gap-3', collapsed && 'justify-center')}>
          {!collapsed && (
            <>
              <img src={BRAND_LOGO_PATH} alt="Cloakbot logo" className="h-10 w-10 shrink-0 object-contain" />
              <p className="min-w-0 flex-1 truncate font-serif text-[1.35rem] leading-none text-foreground">{BRAND_NAME}</p>
            </>
          )}
          {onToggleSidebar && (
            <Button
              variant="ghost"
              size="icon"
              className={cn(
                'shrink-0 cursor-ew-resize bg-transparent text-sidebar-foreground hover:bg-sidebar-accent hover:text-sidebar-accent-foreground',
                collapsed ? 'h-9 w-full rounded-lg px-0' : 'h-8 w-8 rounded-lg'
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

      <div className={cn(sectionPaddingClass, 'pt-4')}>
        {!collapsed && <div className="mb-2 text-[10px] uppercase tracking-[0.18em] text-muted-foreground">Workspace</div>}
        <div className="space-y-1.5">
          {navigationItems.map((item) => {
            const isActive = currentView === item.id
            return (
              <button
                key={item.id}
                type="button"
                onClick={() => onSelectGlobalView(item.id)}
                aria-label={item.name}
                className={cn(
                  'flex h-8 w-full items-center gap-2 rounded-lg px-3 text-left text-[13px] font-medium text-muted-foreground transition-colors',
                  collapsed && 'justify-center px-0',
                  isActive
                    ? 'bg-card text-foreground'
                    : 'hover:bg-sidebar-accent hover:text-foreground',
                )}
              >
                <item.icon className="size-4 shrink-0" />
                {!collapsed && <span className="truncate">{item.name}</span>}
              </button>
            )
          })}
        </div>
      </div>

      <div className={cn(sectionPaddingClass, 'pt-4')}>
        {!collapsed && <div className="mb-2 text-[10px] uppercase tracking-[0.18em] text-muted-foreground">Conversations</div>}
        <Button
          type="button"
          variant="default"
          className={cn(
            'h-9 w-full justify-start gap-2 rounded-lg px-3 text-left text-[13px]',
            collapsed && 'justify-center px-0'
          )}
          onClick={onStartNewSession}
          aria-label="New Chat"
        >
          <Plus className="size-4 shrink-0" />
          {!collapsed && <span className="font-medium">New Chat</span>}
        </Button>
      </div>

      <nav className={cn('min-h-0 flex-1 pb-3 pt-3', sectionPaddingClass)}>
        <div className="space-y-1.5 overflow-y-auto">
          {sessions.map((session) => {
            const isActive = currentView === 'chat' && activeSessionId === session.id
            return (
              <button
                key={session.id}
                type="button"
                onClick={() => onSelectSession(session.id)}
                title={session.title}
                aria-label={session.title}
                aria-current={isActive ? 'true' : undefined}
                className={cn(
                  'h-8 w-full truncate rounded-lg px-3 text-left text-[13px] font-medium text-muted-foreground transition-colors',
                  collapsed && 'px-2 text-center',
                  isActive
                    ? 'bg-card text-foreground'
                    : 'hover:bg-sidebar-accent hover:text-foreground'
                )}
              >
                <span className="block truncate">{session.title}</span>
              </button>
            )
          })}
        </div>
      </nav>

      <GatewayStatus collapsed={collapsed} sectionPaddingClass={sectionPaddingClass} />
    </div>
  )
}

function GatewayStatus({ collapsed, sectionPaddingClass }: { collapsed: boolean; sectionPaddingClass: string }) {
  const [state, setState] = useState<GatewayConnectionState>('checking')
  const [detail, setDetail] = useState('')

  useEffect(() => {
    let cancelled = false
    let timeoutId: number | undefined

    async function refreshStatus() {
      try {
        const response = await fetch('/api/status')
        if (!response.ok) {
          throw new Error(`Gateway status failed: ${response.status}`)
        }

        const payload = await response.json() as { ready?: boolean; model?: string; provider?: string }
        if (cancelled) {
          return
        }

        setState(payload.ready === false ? 'disconnected' : 'connected')
        setDetail([payload.model, payload.provider].filter(Boolean).join(' · '))
      } catch {
        if (!cancelled) {
          setState('disconnected')
          setDetail('')
        }
      } finally {
        if (!cancelled) {
          timeoutId = window.setTimeout(refreshStatus, 15000)
        }
      }
    }

    void refreshStatus()

    return () => {
      cancelled = true
      if (timeoutId) {
        window.clearTimeout(timeoutId)
      }
    }
  }, [])

  const isOnline = state === 'connected'
  const label = isOnline ? 'Gateway: Connected' : 'Gatewat: Disconnected'
  return (
    <div className={cn('border-t border-sidebar-border bg-sidebar-accent/55 py-3', sectionPaddingClass)}>
      <div
        className={cn(
          'flex min-h-11 items-center gap-4 text-[12px] text-muted-foreground',
          collapsed && 'justify-center px-0'
        )}
        aria-label={label}
        title={detail && isOnline ? `${label}: ${detail}` : label}
      >
        <GatewayStatusDot isOnline={isOnline} />
        {!collapsed && (
          <span className="min-w-0 space-y-0.5">
            <span className="block text-xs leading-4 text-muted-foreground">{label}</span>
            {detail && isOnline && <span className="block truncate leading-5">{detail}</span>}
          </span>
        )}
      </div>
    </div>
  )
}

function GatewayStatusDot({ isOnline }: { isOnline: boolean }) {
  return (
    <span className="relative mx-1 flex h-2.5 w-2.5 shrink-0" aria-hidden="true">
      {isOnline && (
        <span className="absolute inline-flex h-full w-full animate-ping rounded-full bg-status-connected/50" />
      )}
      <span
        className={cn(
          'relative inline-flex h-2.5 w-2.5 rounded-full',
          isOnline ? 'bg-status-connected' : 'bg-muted-foreground/50'
        )}
      />
    </span>
  )
}

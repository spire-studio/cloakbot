import type { LucideIcon } from 'lucide-react'
import { Bolt, MessageSquare, Settings } from 'lucide-react'

export type NavigationTabId = 'config' | 'skills'
export type WorkspaceViewId = 'chat' | NavigationTabId

export type NavigationItem = {
  name: string
  icon: LucideIcon
  id: NavigationTabId
  eyebrow: string
  description: string
}

export const chatViewItem = {
  name: 'Conversations',
  icon: MessageSquare,
  id: 'chat' as const,
  eyebrow: 'Workspace Assistant',
  description: 'Review active conversations and jump back into the current chat.',
}

export const navigationItems: NavigationItem[] = [
  {
    name: 'Settings',
    icon: Settings,
    id: 'config',
    eyebrow: 'System Settings',
    description: 'Review workspace settings, tools, and execution preferences.',
  },
  {
    name: 'Skills',
    icon: Bolt,
    id: 'skills',
    eyebrow: 'Tooling Skills',
    description: 'Browse and manage assistant skills and capabilities.',
  },
]

import type { LucideIcon } from 'lucide-react'
import { MessageSquare, Settings } from 'lucide-react'

export type NavigationTabId = 'chat' | 'config'

export type NavigationItem = {
  name: string
  icon: LucideIcon
  id: NavigationTabId
  eyebrow: string
  description: string
}

export const navigationItems: NavigationItem[] = [
  {
    name: 'Chat',
    icon: MessageSquare,
    id: 'chat',
    eyebrow: 'Workspace Assistant',
    description: 'Talk to Cloakbot about code, terminal output, and project context.',
  },
  {
    name: 'Configuration',
    icon: Settings,
    id: 'config',
    eyebrow: 'System Settings',
    description: 'Review workspace settings, tools, and execution preferences.',
  },
]

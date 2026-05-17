import { Eye, EyeOff } from 'lucide-react'

import { Button } from '@/components/ui/button'
import { useRemoteView } from '@/features/chat/context/RemoteViewContext'
import { cn } from '@/lib/utils'

type RemoteViewToggleProps = {
  className?: string
}

/**
 * Header toggle: flip every chat bubble between "what you typed" and
 * "what the remote model saw". Persists in-memory only — first paint is
 * always local so the reveal moment has impact.
 */
export function RemoteViewToggle({ className }: RemoteViewToggleProps) {
  const { isRemote, toggle } = useRemoteView()

  return (
    <Button
      type="button"
      variant={isRemote ? 'default' : 'outline'}
      size="sm"
      onClick={toggle}
      className={cn('h-8 gap-1.5 rounded-lg px-2.5', className)}
      aria-pressed={isRemote}
      aria-label={isRemote ? 'Switch to local view' : 'Switch to remote view'}
      title={isRemote ? 'Showing the sanitized payload' : 'Showing your original text'}
    >
      {isRemote ? <EyeOff className="h-3.5 w-3.5" /> : <Eye className="h-3.5 w-3.5" />}
      <span className="text-[12px] font-medium">{isRemote ? 'Remote view' : 'Local view'}</span>
    </Button>
  )
}

import { Shield } from 'lucide-react'
import { useEffect, useState } from 'react'

import { cn } from '@/lib/utils'

type BlockedCounterProps = {
  total: number
  className?: string
}

/**
 * Live "PII spans blocked this session" badge for the connection chrome.
 *
 * Subtle by default; flashes briefly when the count increments so a viewer
 * notices something landed. Renders nothing at zero so it stays invisible
 * until the privacy layer actually does work.
 */
export function BlockedCounter({ total, className }: BlockedCounterProps) {
  // Track the previous total via state (React "adjust state on prop change"
  // pattern) so the flash trigger is derived during render, not in an effect.
  const [trackedTotal, setTrackedTotal] = useState(total)
  const [flashing, setFlashing] = useState(false)

  if (total !== trackedTotal) {
    setTrackedTotal(total)
    setFlashing(total > trackedTotal)
  }

  useEffect(() => {
    if (!flashing) return
    const timeout = window.setTimeout(() => setFlashing(false), 360)
    return () => window.clearTimeout(timeout)
  }, [flashing])

  if (total <= 0) return null

  return (
    <div
      role="status"
      aria-live="polite"
      aria-label={`${total} private values blocked in this session`}
      className={cn(
        'inline-flex items-center gap-1.5 rounded-full border border-border bg-card px-2.5 py-1 text-[11.5px] font-medium text-foreground transition-shadow duration-200',
        flashing && 'border-amber-400/50 bg-amber-100/70 text-amber-800 shadow-[0_0_0_3px_rgba(251,191,36,0.18)] dark:bg-amber-500/15 dark:text-amber-200',
        className,
      )}
    >
      <Shield className="h-3 w-3 text-muted-foreground" />
      <span className="tabular-nums">{total}</span>
      <span className="text-muted-foreground">blocked</span>
    </div>
  )
}

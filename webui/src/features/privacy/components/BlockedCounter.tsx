import { Shield } from 'lucide-react'
import { useEffect, useState } from 'react'

import { cn } from '@/lib/utils'

type BlockedCounterProps = {
  total: number
  className?: string
}

/**
 * Live "PII spans blocked today" badge for the shell header.
 *
 * Subtle by default; flashes briefly when the count increments so the
 * audience watching a demo notices something landed.
 */
export function BlockedCounter({ total, className }: BlockedCounterProps) {
  // Track the previous total via state (React-recommended "adjust state on
  // prop change" pattern) so we can derive the flash trigger during render
  // instead of inside an effect.
  const [trackedTotal, setTrackedTotal] = useState(total)
  const [flashing, setFlashing] = useState(false)

  if (total !== trackedTotal) {
    setTrackedTotal(total)
    setFlashing(total > trackedTotal)
  }

  useEffect(() => {
    if (!flashing) {
      return
    }
    const timeout = window.setTimeout(() => setFlashing(false), 360)
    return () => window.clearTimeout(timeout)
  }, [flashing])

  return (
    <div
      role="status"
      aria-live="polite"
      aria-label={`${total} private values blocked in this session`}
      className={cn(
        'inline-flex items-center gap-1.5 rounded-full border border-border bg-card px-2.5 py-1 text-[11.5px] font-medium text-foreground transition-shadow duration-200',
        flashing && 'border-[var(--privacy-medium-border)] bg-[var(--privacy-medium-bg)] text-[var(--privacy-medium-text)] shadow-[0_0_0_3px_var(--privacy-medium-bg)]',
        className,
      )}
    >
      <Shield className="h-3 w-3 text-muted-foreground" />
      <span className="tabular-nums">{total}</span>
      <span className="text-muted-foreground">blocked</span>
    </div>
  )
}

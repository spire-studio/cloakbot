/**
 * Self-contained UI primitives for the privacy overlay.
 *
 * The adopted upstream Workbench webui ships ``button`` / ``input`` /
 * ``tooltip`` but not the ``chip`` / ``tabs`` / ``scroll-area`` primitives the
 * salvaged privacy components used. Rather than fork upstream's shared UI, the
 * overlay carries these tiny, dependency-free equivalents so it stays a clean
 * additive module.
 */
import {
  createContext,
  useContext,
  type ButtonHTMLAttributes,
  type HTMLAttributes,
  type ReactNode,
} from 'react'

import { cn } from '@/lib/utils'

/** Display name shown in overlay empty-states. */
export const BRAND_NAME = 'CloakBot'

type ChipProps = HTMLAttributes<HTMLSpanElement> & {
  size?: 'default' | 'roomy'
  variant?: 'outline' | 'fill'
}

/** Compact pill used throughout the inspector for counts / labels / severities. */
export function Chip({ className, size = 'default', variant = 'outline', ...props }: ChipProps) {
  return (
    <span
      className={cn(
        'inline-flex items-center gap-1 rounded-full border text-[11px] font-medium leading-none',
        size === 'roomy' ? 'px-2.5 py-1' : 'px-2 py-0.5',
        variant === 'fill'
          ? 'border-transparent bg-secondary text-secondary-foreground'
          : 'border-border bg-card text-muted-foreground',
        className,
      )}
      {...props}
    />
  )
}

type TabsContextValue = {
  value: string
  setValue: (value: string) => void
}

const TabsContext = createContext<TabsContextValue | null>(null)

export function Tabs({
  value,
  onValueChange,
  className,
  children,
}: {
  value: string
  onValueChange: (value: string) => void
  className?: string
  children: ReactNode
}) {
  return (
    <TabsContext.Provider value={{ value, setValue: onValueChange }}>
      <div className={className}>{children}</div>
    </TabsContext.Provider>
  )
}

export function TabsList({ className, children }: { className?: string; children: ReactNode }) {
  return (
    <div role="tablist" className={cn('inline-flex items-center gap-1 rounded-lg bg-muted/50 p-1', className)}>
      {children}
    </div>
  )
}

export function TabsTrigger({
  value,
  className,
  children,
}: {
  value: string
  className?: string
  children: ReactNode
}) {
  const ctx = useContext(TabsContext)
  const active = ctx?.value === value
  return (
    <button
      type="button"
      role="tab"
      aria-selected={active}
      data-state={active ? 'active' : 'inactive'}
      onClick={() => ctx?.setValue(value)}
      className={cn(
        'inline-flex items-center justify-center gap-1.5 rounded-md px-2.5 py-1.5 text-xs font-medium transition-colors',
        active ? 'bg-card text-foreground shadow-sm' : 'text-muted-foreground hover:text-foreground',
        className,
      )}
    >
      {children}
    </button>
  )
}

export function TabsContent({
  value,
  className,
  children,
}: {
  value: string
  className?: string
  children: ReactNode
}) {
  const ctx = useContext(TabsContext)
  if (ctx?.value !== value) return null
  return (
    <div role="tabpanel" className={className}>
      {children}
    </div>
  )
}

/** Minimal scroll container (upstream has no ``scroll-area`` primitive). */
export function ScrollArea({ className, children }: { className?: string; children: ReactNode }) {
  return <div className={cn('overflow-auto', className)}>{children}</div>
}

type SmallButtonProps = ButtonHTMLAttributes<HTMLButtonElement>

/** Ghost button matching the overlay's density (independent of upstream button). */
export function GhostButton({ className, ...props }: SmallButtonProps) {
  return (
    <button
      type="button"
      className={cn(
        'inline-flex items-center justify-center gap-1.5 rounded-md px-2 py-1 text-[11px] font-medium text-muted-foreground transition-colors',
        'hover:bg-muted/60 hover:text-foreground disabled:pointer-events-none disabled:opacity-50',
        'focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring',
        className,
      )}
      {...props}
    />
  )
}

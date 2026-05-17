/* eslint-disable react-refresh/only-export-components --
 * Context module: co-locating Provider + consumer hook is the documented
 * React context pattern and the canonical export shape for this file.
 */
import {
  createContext,
  useCallback,
  useContext,
  useMemo,
  useState,
  type ReactNode,
} from 'react'

type PrivacyHeaderStats = {
  totalEntities: number
  highSeverityCount: number
  blockedTurns: number
}

type PrivacyStateContextValue = {
  stats: PrivacyHeaderStats
  setStats: (stats: PrivacyHeaderStats) => void
}

const defaultStats: PrivacyHeaderStats = {
  totalEntities: 0,
  highSeverityCount: 0,
  blockedTurns: 0,
}

const PrivacyStateContext = createContext<PrivacyStateContextValue | null>(null)

/**
 * Lifts a small slice of privacy stats out of `ChatPage` so the
 * `ShellHeader` (in a different branch of the tree) can render the live
 * "blocked PII" counter without prop-drilling through `AppShell`.
 */
export function PrivacyStateProvider({ children }: { children: ReactNode }) {
  const [stats, setStatsState] = useState<PrivacyHeaderStats>(defaultStats)

  const setStats = useCallback((next: PrivacyHeaderStats) => {
    setStatsState((current) =>
      current.totalEntities === next.totalEntities &&
      current.highSeverityCount === next.highSeverityCount &&
      current.blockedTurns === next.blockedTurns
        ? current
        : next,
    )
  }, [])

  const value = useMemo<PrivacyStateContextValue>(() => ({ stats, setStats }), [stats, setStats])

  return <PrivacyStateContext.Provider value={value}>{children}</PrivacyStateContext.Provider>
}

export function usePrivacyState(): PrivacyStateContextValue {
  const value = useContext(PrivacyStateContext)
  if (!value) {
    return {
      stats: defaultStats,
      setStats: () => {},
    }
  }
  return value
}

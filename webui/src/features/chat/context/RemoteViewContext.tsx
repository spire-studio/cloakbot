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

export type RemoteViewMode = 'local' | 'remote'

type RemoteViewContextValue = {
  mode: RemoteViewMode
  isRemote: boolean
  toggle: () => void
  setMode: (mode: RemoteViewMode) => void
}

const RemoteViewContext = createContext<RemoteViewContextValue | null>(null)

type RemoteViewProviderProps = {
  children: ReactNode
  defaultMode?: RemoteViewMode
}

/**
 * Global "what did the remote model see?" toggle.
 *
 * Default is `local` — the user sees their original text on first render.
 * Flipping to `remote` re-renders every chat bubble with placeholder
 * substitutions so the audience can compare local vs. sanitized in 1 click.
 */
export function RemoteViewProvider({
  children,
  defaultMode = 'local',
}: RemoteViewProviderProps) {
  const [mode, setMode] = useState<RemoteViewMode>(defaultMode)

  const toggle = useCallback(() => {
    setMode((current) => (current === 'local' ? 'remote' : 'local'))
  }, [])

  const value = useMemo<RemoteViewContextValue>(
    () => ({
      mode,
      isRemote: mode === 'remote',
      toggle,
      setMode,
    }),
    [mode, toggle],
  )

  return <RemoteViewContext.Provider value={value}>{children}</RemoteViewContext.Provider>
}

export function useRemoteView(): RemoteViewContextValue {
  const value = useContext(RemoteViewContext)
  if (!value) {
    // Safe fallback so isolated component tests work without the provider.
    return {
      mode: 'local',
      isRemote: false,
      toggle: () => {},
      setMode: () => {},
    }
  }
  return value
}

import { createContext, useContext } from 'react'

export type ThemeMode = 'light' | 'system' | 'dark'
export type ResolvedTheme = Exclude<ThemeMode, 'system'>

export type ThemeContextValue = {
  theme: ThemeMode
  resolvedTheme: ResolvedTheme
  setTheme: (theme: ThemeMode) => void
}

export const ThemeContext = createContext<ThemeContextValue | null>(null)

export function useTheme() {
  const context = useContext(ThemeContext)
  if (!context) {
    throw new Error('useTheme must be used within a ThemeProvider')
  }

  return context
}

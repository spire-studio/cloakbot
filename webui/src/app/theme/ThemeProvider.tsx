import {
  useEffect,
  useMemo,
  useState,
  type ReactNode,
} from 'react'

import {
  ThemeContext,
  type ThemeContextValue,
  type ThemeMode,
  type ResolvedTheme,
} from './theme-context'

const THEME_STORAGE_KEY = 'cloakbot-theme'

export function ThemeProvider({ children }: { children: ReactNode }) {
  const [theme, setTheme] = useState<ThemeMode>(() => readStoredTheme())
  const [systemTheme, setSystemTheme] = useState<ResolvedTheme>(() => readSystemTheme())

  useEffect(() => {
    if (typeof window === 'undefined' || typeof window.matchMedia !== 'function') {
      return
    }

    const mediaQuery = window.matchMedia('(prefers-color-scheme: dark)')
    const updateSystemTheme = () => {
      setSystemTheme(mediaQuery.matches ? 'dark' : 'light')
    }

    updateSystemTheme()
    mediaQuery.addEventListener('change', updateSystemTheme)

    return () => {
      mediaQuery.removeEventListener('change', updateSystemTheme)
    }
  }, [])

  const resolvedTheme = theme === 'system' ? systemTheme : theme

  useEffect(() => {
    if (typeof document === 'undefined') {
      return
    }

    document.documentElement.classList.toggle('dark', resolvedTheme === 'dark')
  }, [resolvedTheme])

  useEffect(() => {
    if (typeof window === 'undefined') {
      return
    }

    window.localStorage.setItem(THEME_STORAGE_KEY, theme)
  }, [theme])

  const value = useMemo<ThemeContextValue>(
    () => ({
      theme,
      resolvedTheme,
      setTheme,
    }),
    [resolvedTheme, theme],
  )

  return <ThemeContext.Provider value={value}>{children}</ThemeContext.Provider>
}

function readStoredTheme(): ThemeMode {
  if (typeof window === 'undefined') {
    return 'system'
  }

  const storedTheme = window.localStorage.getItem(THEME_STORAGE_KEY)
  return isThemeMode(storedTheme) ? storedTheme : 'system'
}

function readSystemTheme(): ResolvedTheme {
  if (typeof window === 'undefined' || typeof window.matchMedia !== 'function') {
    return 'light'
  }

  return window.matchMedia('(prefers-color-scheme: dark)').matches ? 'dark' : 'light'
}

function isThemeMode(value: string | null): value is ThemeMode {
  return value === 'light' || value === 'system' || value === 'dark'
}

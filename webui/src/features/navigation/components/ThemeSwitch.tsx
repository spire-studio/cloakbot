import { Check, LaptopMinimal, Moon, Sun } from 'lucide-react'

import { useTheme, type ThemeMode } from '@/app/theme/theme-context'
import { Button } from '@/components/ui/button'
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuTrigger,
} from '@/components/ui/dropdown-menu'
import { cn } from '@/lib/utils'

const themeOptions: Array<{
  value: ThemeMode
  label: string
  icon: typeof Sun
}> = [
  { value: 'light', label: 'Light', icon: Sun },
  { value: 'system', label: 'System', icon: LaptopMinimal },
  { value: 'dark', label: 'Dark', icon: Moon },
]

export function ThemeSwitch() {
  const { theme, resolvedTheme, setTheme } = useTheme()
  const TriggerIcon = resolvedTheme === 'dark' ? Moon : Sun

  return (
    <DropdownMenu>
      <DropdownMenuTrigger asChild>
        <Button
          type="button"
          variant="outline"
          size="icon"
          className="h-8 w-8 rounded-lg bg-card"
          aria-label="Theme"
        >
          <TriggerIcon className="size-4" />
        </Button>
      </DropdownMenuTrigger>
      <DropdownMenuContent align="end" className="w-40 rounded-lg">
        {themeOptions.map((option) => {
          const OptionIcon = option.icon

          return (
            <DropdownMenuItem
              key={option.value}
              className="rounded-md"
              onClick={() => setTheme(option.value)}
            >
              <OptionIcon className="size-4" />
              <span>{option.label}</span>
              <Check
                className={cn(
                  'ml-auto size-4',
                  theme === option.value ? 'opacity-100' : 'opacity-0',
                )}
              />
            </DropdownMenuItem>
          )
        })}
      </DropdownMenuContent>
    </DropdownMenu>
  )
}

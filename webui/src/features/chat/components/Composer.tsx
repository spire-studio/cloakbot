import { Send } from 'lucide-react'
import type { KeyboardEvent } from 'react'

import { Button } from '@/components/ui/button'
import { Textarea } from '@/components/ui/textarea'
import { cn } from '@/lib/utils'
import { BRAND_NAME } from '@/shared/constants/brand'

type ComposerProps = {
  input: string
  onInputChange: (value: string) => void
  onSend: () => void
}

export function Composer({ input, onInputChange, onSend }: ComposerProps) {
  const trimmedInput = input.trim()

  const handleKeyDown = (event: KeyboardEvent<HTMLTextAreaElement>) => {
    if (event.key === 'Enter' && !event.shiftKey) {
      event.preventDefault()
      onSend()
    }
  }

  return (
    <div className="shrink-0 border-t border-border/60 bg-background/75 px-4 pb-6 pt-4 backdrop-blur-xl lg:px-6">
      <div className="relative mx-auto max-w-4xl">
        <div className="relative flex w-full items-end overflow-hidden rounded-xl border bg-card shadow-sm transition-shadow focus-within:ring-1 focus-within:ring-ring/50">
          <Textarea
            value={input}
            onChange={(event) => onInputChange(event.target.value)}
            onKeyDown={handleKeyDown}
            placeholder={`Ask ${BRAND_NAME} anything...`}
            className="m-0 min-h-[56px] max-h-[250px] w-full resize-none border-0 bg-transparent py-4 pl-4 pr-14 text-[15px] focus-visible:ring-0"
            rows={1}
          />
          <Button
            size="icon"
            className={cn(
              'absolute bottom-2 right-2 h-9 w-9 shrink-0 rounded-lg transition-all duration-200',
              trimmedInput
                ? 'bg-primary text-primary-foreground opacity-100 hover:bg-primary/90'
                : 'bg-secondary text-muted-foreground opacity-50',
            )}
            onClick={onSend}
            disabled={!trimmedInput}
            aria-label="Send message"
          >
            <Send className="h-4 w-4" />
          </Button>
        </div>
        <div className="mt-3 text-center text-xs text-muted-foreground">
          {BRAND_NAME} can make mistakes. Check important info.
        </div>
      </div>
    </div>
  )
}

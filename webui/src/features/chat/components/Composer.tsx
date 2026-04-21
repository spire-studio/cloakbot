import { Send } from 'lucide-react'
import { useEffect, useRef, type KeyboardEvent } from 'react'

import { Button } from '@/components/ui/button'
import { Textarea } from '@/components/ui/textarea'
import { cn } from '@/lib/utils'
import { BRAND_NAME } from '@/shared/constants/brand'

type ComposerProps = {
  input: string
  onInputChange: (value: string) => void
  onSend: () => void
  isAwaitingAssistant: boolean
  layout?: 'landing' | 'conversation'
  className?: string
}

export function Composer({
  input,
  onInputChange,
  onSend,
  isAwaitingAssistant,
  layout = 'conversation',
  className,
}: ComposerProps) {
  const trimmedInput = input.trim()
  const isSendDisabled = !trimmedInput || isAwaitingAssistant
  const textareaRef = useRef<HTMLTextAreaElement>(null)

  const handleKeyDown = (event: KeyboardEvent<HTMLTextAreaElement>) => {
    if (event.key === 'Enter' && !event.shiftKey) {
      event.preventDefault()
      if (!isSendDisabled) {
        onSend()
      }
    }
  }

  useEffect(() => {
    const textarea = textareaRef.current
    if (!textarea) {
      return
    }

    const minHeight = getTextareaMinHeight(textarea, layout)
    const maxHeight = getTextareaMaxHeight(textarea)
    textarea.style.height = '0px'
    const nextHeight = Math.max(minHeight, Math.min(textarea.scrollHeight, maxHeight))
    textarea.style.height = `${nextHeight}px`
    textarea.style.overflowY = textarea.scrollHeight > maxHeight ? 'auto' : 'hidden'
  }, [input, layout])

  useEffect(() => {
    const handleResize = () => {
      const textarea = textareaRef.current
      if (!textarea) {
        return
      }

      const minHeight = getTextareaMinHeight(textarea, layout)
      const maxHeight = getTextareaMaxHeight(textarea)
      textarea.style.height = '0px'
      const nextHeight = Math.max(minHeight, Math.min(textarea.scrollHeight, maxHeight))
      textarea.style.height = `${nextHeight}px`
      textarea.style.overflowY = textarea.scrollHeight > maxHeight ? 'auto' : 'hidden'
    }

    window.addEventListener('resize', handleResize)
    return () => {
      window.removeEventListener('resize', handleResize)
    }
  }, [layout])

  return (
    <div
      className={cn(
        layout === 'landing'
          ? 'w-full'
          : 'shrink-0 px-4 pb-5 pt-4 lg:px-5',
        className,
      )}
    >
      <div className="relative mx-auto max-w-[52rem]">
        <div className="w-full overflow-hidden rounded-[16px] border border-border bg-card shadow-[0_0_0_1px_var(--surface-outline)] transition-[box-shadow,border-color] duration-200 focus-within:border-border focus-within:shadow-[0_0_0_1px_var(--surface-outline-strong),0_20px_44px_var(--shadow-composer)]">
          <Textarea
            ref={textareaRef}
            value={input}
            onChange={(event) => onInputChange(event.target.value)}
            onKeyDown={handleKeyDown}
            placeholder={`Ask ${BRAND_NAME} anything...`}
            className="m-0 min-h-0 w-full resize-none border-0 bg-transparent px-4 py-4 text-[15px] leading-[1.6] shadow-none focus-visible:ring-0 focus-visible:ring-offset-0 focus-visible:shadow-none"
            rows={layout === 'landing' ? 2 : 1}
          />
          <div className="flex items-center justify-end px-3 py-2">
            <Button
              size="icon"
              variant="default"
              className={cn(
                'h-[2.125rem] w-[2.125rem] shrink-0 rounded-lg transition-all duration-200',
                trimmedInput
                  ? 'opacity-100'
                  : 'border-secondary bg-secondary text-muted-foreground opacity-70 hover:bg-secondary',
              )}
              onClick={onSend}
              disabled={isSendDisabled}
              aria-label="Send message"
            >
              <Send className="h-4 w-4" />
            </Button>
          </div>
        </div>
      </div>
    </div>
  )
}

function getTextareaMinHeight(textarea: HTMLTextAreaElement, layout: ComposerProps['layout']) {
  const computedStyle = window.getComputedStyle(textarea)
  const lineHeight = Number.parseFloat(computedStyle.lineHeight) || 24
  const paddingTop = Number.parseFloat(computedStyle.paddingTop) || 0
  const paddingBottom = Number.parseFloat(computedStyle.paddingBottom) || 0
  const minRows = layout === 'landing' ? 1.33 : 1

  return lineHeight * minRows + paddingTop + paddingBottom
}

function getTextareaMaxHeight(textarea: HTMLTextAreaElement) {
  const computedStyle = window.getComputedStyle(textarea)
  const lineHeight = Number.parseFloat(computedStyle.lineHeight) || 24
  const paddingTop = Number.parseFloat(computedStyle.paddingTop) || 0
  const paddingBottom = Number.parseFloat(computedStyle.paddingBottom) || 0

  return Math.max(lineHeight + paddingTop + paddingBottom, lineHeight * 7 + paddingTop + paddingBottom)
}

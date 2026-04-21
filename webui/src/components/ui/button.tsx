import * as React from "react"
import { Slot } from "@radix-ui/react-slot"
import { cva, type VariantProps } from "class-variance-authority"

import { cn } from "@/lib/utils"

const buttonVariants = cva(
  "inline-flex items-center justify-center gap-2 whitespace-nowrap rounded-lg text-[14px] font-medium leading-none text-secondary-foreground ring-offset-background transition-[background-color,color,box-shadow,border-color,transform] duration-150 ease-out focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-offset-2 active:translate-y-px disabled:pointer-events-none disabled:opacity-50 [&_svg]:pointer-events-none [&_svg]:size-4 [&_svg]:shrink-0",
  {
    variants: {
      variant: {
        default:
          "border border-primary bg-primary text-primary-foreground shadow-[0_0_0_1px_var(--surface-outline)] hover:bg-[var(--primary-hover)] hover:shadow-[0_0_0_1px_var(--surface-outline-strong)] active:shadow-[inset_0_0_0_1px_var(--surface-outline-pressed)]",
        destructive:
          "border border-destructive bg-destructive text-destructive-foreground shadow-[0_0_0_1px_var(--surface-outline)] hover:bg-[var(--destructive-hover)] hover:shadow-[0_0_0_1px_var(--surface-outline-strong)] active:shadow-[inset_0_0_0_1px_var(--surface-outline-pressed)]",
        outline:
          "border border-border bg-secondary text-secondary-foreground shadow-[0_0_0_1px_var(--surface-outline)] hover:bg-accent hover:text-foreground hover:shadow-[0_0_0_1px_var(--surface-outline-strong)] active:shadow-[inset_0_0_0_1px_var(--surface-outline-pressed)]",
        secondary:
          "border border-border bg-card text-foreground shadow-[0_0_0_1px_var(--surface-outline)] hover:bg-[var(--surface-subtle)] hover:shadow-[0_0_0_1px_var(--surface-outline-hover)] active:shadow-[inset_0_0_0_1px_var(--surface-outline-pressed)]",
        ghost: "text-muted-foreground hover:bg-accent hover:text-foreground active:bg-secondary/90",
        link: "text-primary underline-offset-4 hover:underline",
      },
      size: {
        default: "h-[2.375rem] px-3.5 py-2",
        sm: "h-8 px-3 text-[13px]",
        lg: "h-[2.625rem] rounded-xl px-6 text-[15px]",
        icon: "h-9 w-9",
      },
    },
    defaultVariants: {
      variant: "default",
      size: "default",
    },
  }
)

export interface ButtonProps
  extends React.ButtonHTMLAttributes<HTMLButtonElement>,
    VariantProps<typeof buttonVariants> {
  asChild?: boolean
}

const Button = React.forwardRef<HTMLButtonElement, ButtonProps>(
  ({ className, variant, size, asChild = false, ...props }, ref) => {
    const Comp = asChild ? Slot : "button"
    return (
      <Comp
        className={cn(buttonVariants({ variant, size, className }))}
        ref={ref}
        {...props}
      />
    )
  }
)
Button.displayName = "Button"

export { Button }

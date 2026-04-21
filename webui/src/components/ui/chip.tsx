import * as React from "react"
import { cva, type VariantProps } from "class-variance-authority"

import { cn } from "@/lib/utils"

const chipVariants = cva(
  "inline-flex items-center rounded-md border text-[11px] leading-[1.35] whitespace-nowrap",
  {
    variants: {
      variant: {
        outline: "border-border/70 bg-transparent text-muted-foreground",
        fill: "border-border bg-secondary text-secondary-foreground",
      },
      size: {
        default: "px-1.5 py-0.5",
        roomy: "px-2 py-0.5",
      },
    },
    defaultVariants: {
      variant: "outline",
      size: "default",
    },
  },
)

export interface ChipProps
  extends React.HTMLAttributes<HTMLSpanElement>,
    VariantProps<typeof chipVariants> {}

export function Chip({ className, variant, size, ...props }: ChipProps) {
  return <span className={cn(chipVariants({ variant, size, className }))} {...props} />
}

import * as React from 'react';
import { Slot } from '@radix-ui/react-slot';
import { cva, type VariantProps } from 'class-variance-authority';
import { cn } from '@/lib/utils';

/**
 * Boton institucional UrbIA. Variantes alineadas con la paleta UNAL:
 * - default      : azul UNAL solido
 * - accent       : amarillo institucional sobre tinta oscura
 * - outline      : borde primary, fondo transparente
 * - outline-white: borde blanco para usar sobre fondos primary-dark (hero)
 * - ghost        : sin borde, hover sutil
 * - link         : aspecto de hipervinculo
 */
const buttonVariants = cva(
  'inline-flex items-center justify-center gap-2 whitespace-nowrap rounded-md text-sm font-semibold transition-colors ' +
    'focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-primary-light focus-visible:ring-offset-2 ' +
    'disabled:pointer-events-none disabled:opacity-50',
  {
    variants: {
      variant: {
        default: 'bg-primary text-primary-foreground hover:bg-primary-dark shadow-card',
        accent: 'bg-accent text-accent-foreground hover:brightness-95 shadow-card',
        outline: 'border border-primary text-primary bg-transparent hover:bg-primary/5',
        'outline-white':
          'border border-white/70 text-white bg-transparent hover:bg-white/10 backdrop-blur-sm',
        ghost: 'bg-transparent text-ink hover:bg-neutral-100',
        link: 'text-primary underline-offset-4 hover:underline',
        danger: 'bg-danger text-danger-foreground hover:brightness-95',
      },
      size: {
        default: 'h-10 px-4 py-2',
        sm: 'h-8 px-3 text-xs',
        lg: 'h-12 px-6 text-base',
        icon: 'h-10 w-10',
      },
    },
    defaultVariants: { variant: 'default', size: 'default' },
  },
);

export interface ButtonProps
  extends React.ButtonHTMLAttributes<HTMLButtonElement>,
    VariantProps<typeof buttonVariants> {
  asChild?: boolean;
}

export const Button = React.forwardRef<HTMLButtonElement, ButtonProps>(
  ({ className, variant, size, asChild = false, ...props }, ref) => {
    const Comp = asChild ? Slot : 'button';
    return (
      <Comp
        ref={ref}
        className={cn(buttonVariants({ variant, size }), className)}
        {...props}
      />
    );
  },
);
Button.displayName = 'Button';

export { buttonVariants };

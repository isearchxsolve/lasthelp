/**
 * Studio Button — Radix Slot + Tailwind v4.
 * See DESIGN.md §4.1. Stub: structure + variants only, no full styling yet.
 */
import { Slot } from '@radix-ui/react-slot';
import { forwardRef } from 'react';

type Variant = 'primary' | 'secondary' | 'ghost' | 'danger' | 'icon';
type Size = 'sm' | 'md' | 'lg';

export interface ButtonProps extends React.ButtonHTMLAttributes<HTMLButtonElement> {
  variant?: Variant;
  size?: Size;
  loading?: boolean;
  asChild?: boolean;
}

const base =
  'inline-flex items-center justify-center gap-2 font-medium select-none ' +
  'transition-colors duration-150 ease-out disabled:opacity-50 disabled:cursor-not-allowed ' +
  'focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[var(--accent)] focus-visible:ring-offset-2 ' +
  'focus-visible:ring-offset-[var(--surface-panel)]';

const variants: Record<Variant, string> = {
  primary:   'bg-[var(--accent)] text-white hover:bg-[var(--accent-hover)] active:bg-[var(--accent-pressed)]',
  secondary: 'bg-[var(--surface-panel-raised)] text-[var(--text-primary)] border border-[var(--border-default)] hover:bg-[var(--surface-hover)]',
  ghost:     'bg-transparent text-[var(--text-secondary)] hover:bg-[var(--surface-hover)] hover:text-[var(--text-primary)]',
  danger:    'bg-[var(--danger)] text-white hover:opacity-90',
  icon:      'bg-transparent text-[var(--text-secondary)] hover:bg-[var(--surface-hover)] hover:text-[var(--text-primary)] p-2',
};

const sizes: Record<Size, string> = {
  sm: 'h-7 px-2.5 text-xs rounded-md',
  md: 'h-9 px-3.5 text-sm rounded-md',
  lg: 'h-11 px-5 text-base rounded-lg',
};

export const Button = forwardRef<HTMLButtonElement, ButtonProps>(
  ({ variant = 'secondary', size = 'md', loading, asChild, className, children, disabled, ...props }, ref) => {
    const Comp = asChild ? Slot : 'button';
    return (
      <Comp
        ref={ref}
        className={[base, variants[variant], sizes[size], className].filter(Boolean).join(' ')}
        disabled={disabled || loading}
        aria-busy={loading || undefined}
        {...props}
      >
        {loading ? <Spinner /> : children}
      </Comp>
    );
  },
);
Button.displayName = 'Button';

function Spinner() {
  return (
    <svg className="animate-spin h-3.5 w-3.5" viewBox="0 0 24 24" aria-hidden="true">
      <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4" fill="none" />
      <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.4 0 0 5.4 0 12h4z" />
    </svg>
  );
}

import { clsx } from 'clsx';

interface SpinnerProps {
  size?: number; // px
  className?: string;
  label?: string;
}

// FIX: The <progress> element with aria-label is semantically correct for an
// indeterminate loading state. Added role="status" so screen readers announce
// the loading state when the spinner is inserted into the DOM. Callers that
// wrap the spinner in an aria-live region get announcement for free.
export function Spinner({ size = 24, className, label = 'Loading' }: SpinnerProps) {
  return (
    <progress
      role="status"
      aria-label={label}
      aria-live="polite"
      className={clsx('loading-spinner', className)}
      style={{ '--size': `${size}px` } as React.CSSProperties}
    />
  );
}

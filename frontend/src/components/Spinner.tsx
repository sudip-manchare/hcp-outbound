import { clsx } from 'clsx';

interface SpinnerProps {
  size?: number; // px
  className?: string;
  label?: string;
}

export function Spinner({ size = 24, className, label = 'Loading' }: SpinnerProps) {
  return (
    <progress
      aria-label={label}
      className={clsx('loading-spinner', className)}
      style={{ '--size': `${size}px` } as React.CSSProperties}
    />
  );
}

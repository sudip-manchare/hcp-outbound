import { clsx } from 'clsx';

export type BadgeVariant = 'verified' | 'mismatch' | 'velocity' | 'unreviewed' | 'critical' | 'high' | 'medium' | 'low' | 'specialty' | 'tiger';

interface BadgeProps {
  variant: BadgeVariant;
  label: string;
  className?: string;
  size?: 'sm' | 'md';
}

const VARIANT_STYLES: Record<BadgeVariant, string> = {
  verified: 'bg-emerald-500/15 text-emerald-400 border border-emerald-500/30',
  mismatch: 'bg-red-500/15 text-red-400 border border-red-500/30',
  velocity: 'bg-amber-500/15 text-amber-400 border border-amber-500/30',
  unreviewed: 'bg-amber-500/15 text-amber-300 border border-amber-500/30',
  critical: 'bg-red-500/20 text-red-300 border border-red-500/40',
  high: 'bg-orange-500/15 text-orange-400 border border-orange-500/30',
  medium: 'bg-amber-500/15 text-amber-400 border border-amber-500/30',
  low: 'bg-slate-500/15 text-slate-400 border border-slate-500/30',
  specialty: 'bg-blue-500/15 text-blue-400 border border-blue-500/30',
  tiger: 'bg-orange-500/15 text-orange-400 border border-orange-500/30',
};

const VARIANT_ICONS: Partial<Record<BadgeVariant, string>> = {
  verified: '✓',
  mismatch: '⚠',
  velocity: '⚡',
  critical: '🔴',
  high: '🟠',
  unreviewed: '⏳',
};

export function Badge({ variant, label, className, size = 'sm' }: BadgeProps) {
  const icon = VARIANT_ICONS[variant];
  return (
    <span
      className={clsx(
        'inline-flex items-center gap-1 rounded-full font-medium',
        size === 'sm' ? 'px-2 py-0.5 text-xs' : 'px-3 py-1 text-sm',
        VARIANT_STYLES[variant],
        className,
      )}
    >
      {icon && <span aria-hidden>{icon}</span>}
      {label}
    </span>
  );
}

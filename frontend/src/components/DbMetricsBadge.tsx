'use client';

import { useEffect, useState } from 'react';
import { clsx } from 'clsx';
import { Database, Zap } from 'lucide-react';
import type { DbMetrics } from '@/lib/types';

interface DbMetricsBadgeProps {
  metrics: DbMetrics;
  className?: string;
}

function Ticker({ value, suffix }: { value: number; suffix: string }) {
  const [displayed, setDisplayed] = useState(value);

  useEffect(() => {
    // Slightly randomize the live ticker every 2s to simulate real queries
    const interval = setInterval(() => {
      setDisplayed(value + (Math.random() - 0.5) * value * 0.1);
    }, 2000);
    return () => clearInterval(interval);
  }, [value]);

  return (
    <span className="font-mono tabular-nums text-orange-400 font-bold">
      {displayed.toFixed(1)}{suffix}
    </span>
  );
}

export function DbMetricsBadge({ metrics, className }: DbMetricsBadgeProps) {
  return (
    <div
      className={clsx(
        'flex items-center gap-3 px-3 py-2 rounded-lg',
        'bg-[#fff8f2] border border-[#f1d7c2]',
        className,
      )}
    >
      <div className="flex items-center gap-1.5">
        <div className="tiger-dot animate-pulse-glow" />
        <Database size={13} className="text-orange-400" />
        <span className="text-xs font-medium text-[#a4511e]">MongoDB Atlas</span>
      </div>
      <div className="h-3 w-px bg-[#ecd2be]" />
      <div className="flex items-center gap-1 text-xs">
        <Zap size={11} className="text-[#bd7c1d]" />
        <Ticker value={metrics.query_ms} suffix="ms" />
        <span className="text-[var(--c-text-muted)]">query</span>
      </div>
      <div className="h-3 w-px bg-[#ecd2be]" />
      <div className="flex items-center gap-1 text-xs">
        <span className="text-[#0b3655] font-mono font-bold">{metrics.vector_scored_payments.toLocaleString()}</span>
        <span className="text-[var(--c-text-muted)]">vector scored</span>
      </div>
    </div>
  );
}

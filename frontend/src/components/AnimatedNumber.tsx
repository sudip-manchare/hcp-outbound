'use client';

import { useEffect, useRef, useState } from 'react';
import { clsx } from 'clsx';

interface AnimatedNumberProps {
  value: number;
  format?: (n: number) => string;
  duration?: number; // ms
  className?: string;
}

const defaultFormat = (n: number) =>
  n >= 1000
    ? `$${(n / 1000).toFixed(1)}k`
    : n % 1 === 0
    ? n.toString()
    : n.toFixed(1);

export function AnimatedNumber({
  value,
  format = defaultFormat,
  duration = 800,
  className,
}: AnimatedNumberProps) {
  const [displayed, setDisplayed] = useState(0);
  const rafRef = useRef<number | null>(null);
  const startRef = useRef<number | null>(null);
  const startValueRef = useRef(0);

  useEffect(() => {
    if (rafRef.current) cancelAnimationFrame(rafRef.current);
    startValueRef.current = displayed;
    startRef.current = null;

    const animate = (timestamp: number) => {
      if (!startRef.current) startRef.current = timestamp;
      const elapsed = timestamp - startRef.current;
      const progress = Math.min(elapsed / duration, 1);
      // Ease out cubic
      const eased = 1 - Math.pow(1 - progress, 3);
      const current = startValueRef.current + (value - startValueRef.current) * eased;
      setDisplayed(current);
      if (progress < 1) {
        rafRef.current = requestAnimationFrame(animate);
      }
    };

    rafRef.current = requestAnimationFrame(animate);
    return () => {
      if (rafRef.current) cancelAnimationFrame(rafRef.current);
    };
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [value, duration]);

  return (
    <span className={clsx('font-mono-feature tabular-nums', className)}>
      {format(displayed)}
    </span>
  );
}

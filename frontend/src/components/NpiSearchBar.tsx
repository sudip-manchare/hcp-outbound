'use client';

import { useCallback, useRef, useState } from 'react';
import { Search, X, CheckCircle, AlertCircle } from 'lucide-react';
import { clsx } from 'clsx';
import { enrichNpi, isValidNpi } from '@/lib/api';
import { Spinner } from './Spinner';
import type { NppesEnrichment } from '@/lib/types';

interface NpiSearchBarProps {
  onResult?: (enrichment: NppesEnrichment) => void;
}

export function NpiSearchBar({ onResult }: NpiSearchBarProps) {
  const [query, setQuery] = useState('');
  const [status, setStatus] = useState<'idle' | 'loading' | 'success' | 'error'>('idle');
  const [result, setResult] = useState<NppesEnrichment | null>(null);
  const [errorMsg, setErrorMsg] = useState('');
  const debounceRef = useRef<ReturnType<typeof setTimeout> | null>(null);

  const lookup = useCallback(async (npi: string) => {
    if (!isValidNpi(npi)) return;
    setStatus('loading');
    setResult(null);
    setErrorMsg('');
    try {
      const enrichment = await enrichNpi(npi);
      setResult(enrichment);
      setStatus('success');
      onResult?.(enrichment);
    } catch (e) {
      setErrorMsg(e instanceof Error ? e.message : 'NPI not found');
      setStatus('error');
    }
  }, [onResult]);

  const handleChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    const value = e.target.value.replace(/\D/g, '').slice(0, 10);
    setQuery(value);
    setStatus('idle');
    setResult(null);
    if (debounceRef.current) clearTimeout(debounceRef.current);
    if (value.length === 10) {
      debounceRef.current = setTimeout(() => lookup(value), 400);
    }
  };

  const clear = () => {
    setQuery('');
    setStatus('idle');
    setResult(null);
    setErrorMsg('');
  };

  return (
    <div className="space-y-2">
      <div className="relative">
        <Search
          size={15}
          className="absolute left-3 top-1/2 -translate-y-1/2 text-slate-500 pointer-events-none"
        />
        <input
          type="text"
          inputMode="numeric"
          placeholder="Live NPI Lookup — enter 10-digit NPI..."
          value={query}
          onChange={handleChange}
          className={clsx(
            'w-full bg-[#071720] border rounded-lg pl-9 pr-10 py-2.5 text-sm',
            'text-[var(--c-text-primary)] placeholder:text-[var(--c-text-dim)]',
            'focus:outline-none focus:ring-2 transition-all',
            status === 'success' && 'border-[#0d9388] focus:ring-[#0d9388]/20',
            status === 'error' && 'border-[#bf4d4a] focus:ring-[#bf4d4a]/20',
            status === 'loading' && 'border-[#0b3655] focus:ring-[#0b3655]/20',
            status === 'idle' && 'border-[var(--c-border)] focus:ring-[#0d9388]/20',
          )}
          aria-label="NPI Number Search"
          aria-describedby={result ? 'npi-result' : undefined}
        />
        <div className="absolute right-3 top-1/2 -translate-y-1/2">
          {status === 'loading' && <Spinner size={16} />}
          {status === 'success' && <CheckCircle size={16} className="text-emerald-400" />}
          {status === 'error' && <AlertCircle size={16} className="text-red-400" />}
          {query && status === 'idle' && (
            <button onClick={clear} className="text-[var(--c-text-muted)] hover:text-[var(--c-text-primary)]" aria-label="Clear">
              <X size={14} />
            </button>
          )}
        </div>
      </div>

      {/* Result card */}
      {result && (
        <div
          id="npi-result"
          className="rounded-lg border border-[#22625f] bg-[#0d373a] p-3 space-y-1 animate-slide-up"
          role="status"
          aria-live="polite"
        >
          <div className="flex items-center justify-between">
            <span className="text-sm font-semibold text-[var(--c-text-primary)]">{result.legal_name}</span>
            <span className="text-xs text-[#78e3d7] flex items-center gap-1">
              <CheckCircle size={11} /> NPPES Verified
            </span>
          </div>
          <div className="flex flex-wrap gap-x-3 gap-y-1 text-xs text-[var(--c-text-secondary)]">
            <span className="text-[#78e3d7] font-mono">{result.npi}</span>
            <span>{result.taxonomy_desc}</span>
            <span>{result.address.city}, {result.address.state}</span>
          </div>
        </div>
      )}

      {status === 'error' && (
        <p className="text-xs text-[#bf4d4a] pl-1" role="alert">{errorMsg}</p>
      )}
      {query.length > 0 && query.length < 10 && (
        <p className="text-xs text-[var(--c-text-muted)] pl-1">{10 - query.length} more digits needed</p>
      )}
    </div>
  );
}

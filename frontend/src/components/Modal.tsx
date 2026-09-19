'use client';

import { useEffect, useRef } from 'react';
import { clsx } from 'clsx';
import { X } from 'lucide-react';

interface ModalProps {
  open: boolean;
  onClose: () => void;
  title?: string;
  children: React.ReactNode;
  className?: string;
  /* closedby="any" enables native light dismiss (clicking backdrop closes) */
  lightDismiss?: boolean;
}

export function Modal({
  open,
  onClose,
  title,
  children,
  className,
  lightDismiss = true,
}: ModalProps) {
  const dialogRef = useRef<HTMLDialogElement>(null);

  useEffect(() => {
    const dialog = dialogRef.current;
    if (!dialog) return;
    if (open) {
      if (!dialog.open) dialog.showModal();
    } else {
      dialog.close();
    }
  }, [open]);

  // Handle light-dismiss (click on backdrop = native ::backdrop area)
  const handleClick = (e: React.MouseEvent<HTMLDialogElement>) => {
    if (!lightDismiss) return;
    const dialog = dialogRef.current;
    if (!dialog) return;
    const rect = dialog.getBoundingClientRect();
    const isBackdrop =
      e.clientX < rect.left ||
      e.clientX > rect.right ||
      e.clientY < rect.top ||
      e.clientY > rect.bottom;
    if (isBackdrop) onClose();
  };

  return (
    <dialog
      ref={dialogRef}
      onClose={onClose}
      onClick={handleClick}
      /* closedby attribute for native light dismiss (progressive enhancement) */
      {...(lightDismiss ? { closedby: 'any' } : {})}
      className="rounded-xl focus-visible:outline-none"
    >
      <div
        className={clsx(
          'glass-strong rounded-xl p-6 w-full',
          className,
        )}
        onClick={(e) => e.stopPropagation()}
      >
        {(title || lightDismiss) && (
          <div className="flex items-center justify-between mb-5">
            {title && (
              <h2 className="text-lg font-semibold text-[var(--c-text-primary)]">{title}</h2>
            )}
            <button
              onClick={onClose}
              className="ml-auto p-1.5 rounded-lg hover:bg-[#f1f6f7] text-[var(--c-text-muted)] hover:text-[var(--c-text-primary)] transition-colors"
              aria-label="Close"
            >
              <X size={18} />
            </button>
          </div>
        )}
        {children}
      </div>
    </dialog>
  );
}

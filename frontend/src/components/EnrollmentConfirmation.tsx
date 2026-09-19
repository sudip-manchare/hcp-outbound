'use client';

import { motion } from 'framer-motion';
import { CheckCircle, Shield, Star } from 'lucide-react';
import type { Physician } from '@/lib/types';

interface EnrollmentConfirmationProps {
  physician: Physician;
}

export function EnrollmentConfirmation({ physician }: EnrollmentConfirmationProps) {
  return (
    <div className="flex flex-col items-center justify-center h-full px-5 py-6 text-center">
      {/* Animated success ring */}
      <motion.div
        initial={{ scale: 0, opacity: 0 }}
        animate={{ scale: 1, opacity: 1 }}
        transition={{ type: 'spring', damping: 15, stiffness: 200 }}
        className="relative mb-5"
      >
        <div className="w-20 h-20 rounded-full bg-gradient-to-br from-emerald-400 to-emerald-600 flex items-center justify-center shadow-lg">
          <CheckCircle size={36} className="text-white" strokeWidth={2.5} />
        </div>
        {/* Pulse ring */}
        <motion.div
          className="absolute inset-0 rounded-full border-2 border-emerald-400"
          animate={{ scale: [1, 1.5], opacity: [0.8, 0] }}
          transition={{ duration: 1.5, repeat: Infinity }}
        />
      </motion.div>

      <motion.div
        initial={{ y: 20, opacity: 0 }}
        animate={{ y: 0, opacity: 1 }}
        transition={{ delay: 0.3 }}
        className="space-y-2"
      >
        <h3 className="text-base font-bold text-[var(--c-text-primary)]">Notice ready for review</h3>
        <p className="text-xs text-[var(--c-text-secondary)]">
          Dr. {physician.nppes.last_name}, your formal dispute notice is ready for review with{' '}
            <span className="text-[var(--c-text-primary)] font-medium">
            {physician.payments.find((p) => !p.reviewed)?.manufacturer ?? 'the manufacturer'}
          </span>{' '}
          per 42 CFR § 403.908.
        </p>
      </motion.div>

      {/* FalsePay enrollment confirmation */}
      <motion.div
        initial={{ y: 20, opacity: 0 }}
        animate={{ y: 0, opacity: 1 }}
        transition={{ delay: 0.5 }}
        className="mt-5 w-full bg-[#f3fbfa] border border-[#bde7e1] rounded-2xl p-4"
      >
        <div className="flex items-center gap-2 mb-3">
          <Shield size={16} className="text-[#0d9388]" />
          <p className="text-sm font-bold text-[#154c5f]">Ongoing monitoring active</p>
        </div>
        <div className="space-y-2 text-left">
          {[
            'Year-round CMS payment monitoring',
            'Real-time Open Payments anomaly alerts',
            'Dedicated compliance concierge',
            'Auto-dispute for rogue entries',
          ].map((benefit) => (
            <div key={benefit} className="flex items-center gap-2">
              <Star size={10} className="text-[#0d9388] flex-shrink-0" />
              <p className="text-xs text-[var(--c-text-secondary)]">{benefit}</p>
            </div>
          ))}
        </div>
      </motion.div>

      <motion.p
        initial={{ opacity: 0 }}
        animate={{ opacity: 1 }}
        transition={{ delay: 0.8 }}
        className="mt-4 text-xs text-[var(--c-text-muted)] leading-relaxed"
      >
        Review the notice before submitting it through the applicable CMS Open Payments process.
      </motion.p>
    </div>
  );
}

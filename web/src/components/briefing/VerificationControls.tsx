import React, { useState } from 'react';
import { Check, Edit3, X, AlertCircle } from 'lucide-react';
import { VerificationStatus } from '../../types/api';
import { useAuthStore } from '../../stores/authStore';

interface VerificationControlsProps {
  recommendationId: string;
  currentStatus: VerificationStatus;
  onVerify: (recId: string, action: VerificationStatus, note?: string) => Promise<void>;
  disabled?: boolean;
}

export const VerificationControls: React.FC<VerificationControlsProps> = ({
  recommendationId,
  currentStatus,
  onVerify,
  disabled = false,
}) => {
  const { user } = useAuthStore();
  const [modalAction, setModalAction] = useState<VerificationStatus | null>(null);
  const [note, setNote] = useState('');
  const [error, setError] = useState<string | null>(null);
  const [isSubmitting, setIsSubmitting] = useState(false);

  // Hidden unless user is ADMIN
  if (!user || user.role !== 'ADMIN') {
    return null;
  }

  // Already resolved
  if (currentStatus !== 'PENDING') {
    return null;
  }

  const handleApprove = async () => {
    try {
      setIsSubmitting(true);
      await onVerify(recommendationId, 'VERIFIED');
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : 'Approval failed');
    } finally {
      setIsSubmitting(false);
    }
  };

  const handleOpenModal = (action: VerificationStatus) => {
    setModalAction(action);
    setNote('');
    setError(null);
  };

  const handleModalSubmit = async () => {
    if (!note.trim()) {
      setError('A justification note is strictly required for override or rejection.');
      return;
    }
    if (!modalAction) return;

    try {
      setIsSubmitting(true);
      await onVerify(recommendationId, modalAction, note.trim());
      setModalAction(null);
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : 'Action failed');
    } finally {
      setIsSubmitting(false);
    }
  };

  return (
    <div className="mt-3 pt-3 border-t border-slate-800">
      <div className="flex items-center justify-between">
        <span className="text-xs text-slate-400 font-medium">Human Verification Gate (Admin):</span>
        <div className="flex items-center gap-2">
          <button
            type="button"
            disabled={disabled || isSubmitting}
            onClick={handleApprove}
            className="inline-flex items-center gap-1 px-2.5 py-1 text-xs font-semibold text-emerald-300 bg-emerald-950/80 hover:bg-emerald-900 border border-emerald-700/60 rounded transition-colors"
          >
            <Check className="w-3.5 h-3.5" />
            Approve
          </button>

          <button
            type="button"
            disabled={disabled || isSubmitting}
            onClick={() => handleOpenModal('OVERRIDDEN')}
            className="inline-flex items-center gap-1 px-2.5 py-1 text-xs font-semibold text-amber-300 bg-amber-950/80 hover:bg-amber-900 border border-amber-700/60 rounded transition-colors"
          >
            <Edit3 className="w-3.5 h-3.5" />
            Override
          </button>

          <button
            type="button"
            disabled={disabled || isSubmitting}
            onClick={() => handleOpenModal('REJECTED')}
            className="inline-flex items-center gap-1 px-2.5 py-1 text-xs font-semibold text-rose-300 bg-rose-950/80 hover:bg-rose-900 border border-rose-800/60 rounded transition-colors"
          >
            <X className="w-3.5 h-3.5" />
            Reject
          </button>
        </div>
      </div>

      {error && (
        <div className="mt-2 text-xs text-rose-400 flex items-center gap-1">
          <AlertCircle className="w-3.5 h-3.5 flex-shrink-0" />
          {error}
        </div>
      )}

      {/* Note Requirement Modal */}
      {modalAction && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/70 backdrop-blur-sm p-4">
          <div className="bg-slate-900 border border-slate-700 rounded-lg p-5 w-full max-w-md shadow-2xl">
            <h3 className="text-sm font-semibold text-slate-100 flex items-center gap-2 mb-2">
              <AlertCircle className="w-4 h-4 text-amber-400" />
              {modalAction === 'OVERRIDDEN' ? 'Override Recommendation' : 'Reject Recommendation'}
            </h3>
            <p className="text-xs text-slate-400 mb-3">
              Per system safety invariants, an audit-logged justification note is required to {modalAction.toLowerCase()} this recommendation.
            </p>

            <textarea
              value={note}
              onChange={(e) => setNote(e.target.value)}
              placeholder="Enter field observation or operational justification..."
              rows={3}
              className="w-full text-xs bg-slate-950 border border-slate-700 rounded p-2.5 text-slate-100 focus:outline-none focus:border-amber-500 mb-3"
            />

            {error && (
              <p className="text-xs text-rose-400 mb-3">{error}</p>
            )}

            <div className="flex items-center justify-end gap-2">
              <button
                type="button"
                onClick={() => setModalAction(null)}
                className="px-3 py-1.5 text-xs text-slate-300 hover:bg-slate-800 rounded"
              >
                Cancel
              </button>
              <button
                type="button"
                disabled={isSubmitting}
                onClick={handleModalSubmit}
                className="px-3 py-1.5 text-xs font-medium text-white bg-amber-600 hover:bg-amber-500 rounded"
              >
                Confirm {modalAction === 'OVERRIDDEN' ? 'Override' : 'Rejection'}
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
};

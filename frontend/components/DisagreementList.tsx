'use client';

import { useState } from 'react';
import type { DisagreementsResponse, DisagreementFlag } from '@/lib/types';

const SEVERITY_STYLES: Record<string, string> = {
  high:   'bg-red-100 text-red-800 border-red-200',
  medium: 'bg-amber-100 text-amber-800 border-amber-200',
  low:    'bg-slate-100 text-slate-700 border-slate-200',
};

const TYPE_LABELS: Record<string, string> = {
  direction_conflict:   'Direction Conflict',
  evidence_absent:      'Evidence Absent',
  score_gap:            'Score Gap',
  score_text_mismatch:  'Score/Text Mismatch',
};

function FlagCard({ flag }: { flag: DisagreementFlag }) {
  const severityStyle = SEVERITY_STYLES[flag.severity] ?? SEVERITY_STYLES.low;
  const typeLabel = TYPE_LABELS[flag.disagreement_type] ?? flag.disagreement_type;

  return (
    <div className="border border-slate-200 rounded-lg p-4 bg-white space-y-2">
      <div className="flex items-start justify-between gap-3">
        <div>
          <p className="text-sm font-medium text-slate-800">{flag.competency_name}</p>
          <p className="text-xs text-slate-500 mt-0.5">{typeLabel}</p>
        </div>
        <span className={`text-xs px-2 py-0.5 rounded border shrink-0 ${severityStyle}`}>
          {flag.severity}
        </span>
      </div>

      <p className="text-sm text-slate-700">{flag.description}</p>

      {flag.interviewer_names.length > 0 && (
        <p className="text-xs text-slate-400">
          Interviewers: {flag.interviewer_names.join(' vs ')}
        </p>
      )}

      {flag.resolution_suggestion && (
        <div className="bg-slate-50 rounded p-2 text-xs text-slate-600">
          <span className="font-medium">Suggestion: </span>
          {flag.resolution_suggestion}
        </div>
      )}
    </div>
  );
}

interface DisagreementListProps {
  disagreements: DisagreementsResponse;
}

export function DisagreementList({ disagreements }: DisagreementListProps) {
  const [mediumExpanded, setMediumExpanded] = useState(false);

  if (disagreements.total_flags === 0) {
    return (
      <div className="text-sm text-slate-500 bg-emerald-50 border border-emerald-200 rounded-md p-4">
        No disagreements detected across interviewers.
      </div>
    );
  }

  const highFlags   = disagreements.flags.filter(f => f.severity === 'high');
  const mediumFlags = disagreements.flags.filter(f => f.severity === 'medium');
  const lowFlags    = disagreements.flags.filter(f => f.severity === 'low');
  const secondary   = [...mediumFlags, ...lowFlags];

  return (
    <div className="space-y-4">
      <div className="flex items-center gap-4 text-xs text-slate-500">
        <span className="text-red-600 font-medium">{disagreements.high_severity_count} high</span>
        <span className="text-amber-600 font-medium">{disagreements.medium_severity_count} medium</span>
        <span>{disagreements.total_flags} total</span>
      </div>

      {highFlags.length > 0 && (
        <div className="space-y-3">
          <h4 className="text-xs font-semibold text-red-700 uppercase tracking-wide">
            Requires Committee Discussion
          </h4>
          {highFlags.map(flag => <FlagCard key={flag.flag_id} flag={flag} />)}
        </div>
      )}

      {secondary.length > 0 && (
        <div className="space-y-3">
          <button
            onClick={() => setMediumExpanded(v => !v)}
            className="flex items-center gap-2 text-xs font-semibold text-amber-700 uppercase tracking-wide hover:text-amber-900"
          >
            <span>{mediumExpanded ? '▾' : '▸'}</span>
            Notable Divergences ({secondary.length})
          </button>
          {mediumExpanded && secondary.map(flag => <FlagCard key={flag.flag_id} flag={flag} />)}
        </div>
      )}
    </div>
  );
}

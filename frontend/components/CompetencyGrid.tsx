import type { CoverageMapResponse } from '@/lib/types';

const STATUS_STYLES: Record<string, { badge: string; label: string }> = {
  strong:      { badge: 'bg-emerald-100 text-emerald-800 border-emerald-200', label: 'Strong' },
  partial:     { badge: 'bg-amber-100 text-amber-800 border-amber-200',       label: 'Partial' },
  not_covered: { badge: 'bg-red-100 text-red-800 border-red-200',             label: 'Not Covered' },
  conflicted:  { badge: 'bg-purple-100 text-purple-800 border-purple-200',    label: 'Conflicted' },
};

interface CompetencyGridProps {
  coverage: CoverageMapResponse;
}

export function CompetencyGrid({ coverage }: CompetencyGridProps) {
  return (
    <div className="space-y-4">
      <div className="flex items-center justify-between">
        <h3 className="text-sm font-medium text-slate-700">Coverage by Competency</h3>
        <span className="text-sm text-slate-500">
          {coverage.overall_coverage_pct.toFixed(0)}% overall
        </span>
      </div>

      {/* Legend */}
      <div className="flex flex-wrap gap-3 text-xs">
        {Object.entries(STATUS_STYLES).map(([status, { badge, label }]) => (
          <span key={status} className={`px-2 py-0.5 rounded border ${badge}`}>
            {label}
          </span>
        ))}
      </div>

      <div className="grid gap-3 sm:grid-cols-2">
        {coverage.competency_assessments.map((ca) => {
          const style = STATUS_STYLES[ca.coverage_status] ?? STATUS_STYLES.not_covered;
          const pos = ca.positive_evidence.length;
          const neg = ca.negative_evidence.length;
          const vague = ca.vague_claims.length;

          return (
            <div key={ca.competency_id} className="border border-slate-200 rounded-lg p-3 bg-white space-y-2">
              <div className="flex items-center justify-between gap-2">
                <p className="text-sm font-medium text-slate-800 truncate">{ca.competency_name}</p>
                <span className={`text-xs px-2 py-0.5 rounded border shrink-0 ${style.badge}`}>
                  {style.label}
                </span>
              </div>
              <div className="flex gap-3 text-xs text-slate-500">
                <span className="text-emerald-600">{pos} positive</span>
                <span className="text-red-600">{neg} negative</span>
                {vague > 0 && <span className="text-amber-600">{vague} vague</span>}
              </div>
              {ca.assessments_by_interviewer.length > 0 && (
                <p className="text-xs text-slate-400">
                  {ca.assessments_by_interviewer.map((a) => a.interviewer_name).join(', ')}
                </p>
              )}
            </div>
          );
        })}
      </div>

      {coverage.coverage_gaps.length > 0 && (
        <div className="mt-4 space-y-2">
          <h4 className="text-sm font-medium text-slate-700">Coverage Gaps</h4>
          {coverage.coverage_gaps.map((gap) => (
            <div
              key={gap.competency_id}
              className="bg-amber-50 border border-amber-200 rounded-md p-3 text-sm"
            >
              <span className="font-medium text-amber-900">{gap.competency_name}</span>
              <span className="text-amber-700"> — {gap.suggested_followup}</span>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}

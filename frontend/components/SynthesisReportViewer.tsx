import type { SynthesisReport } from '@/lib/types';

const STATUS_STYLES: Record<string, string> = {
  strong:      'text-emerald-700 bg-emerald-50 border-emerald-200',
  partial:     'text-amber-700 bg-amber-50 border-amber-200',
  not_covered: 'text-red-700 bg-red-50 border-red-200',
  conflicted:  'text-purple-700 bg-purple-50 border-purple-200',
};

interface SynthesisReportViewerProps {
  report: SynthesisReport;
}

export function SynthesisReportViewer({ report }: SynthesisReportViewerProps) {
  return (
    <div className="space-y-6">
      {/* No recommendation banner — always visible */}
      <div className="bg-blue-50 border border-blue-200 rounded-md px-4 py-3 text-sm text-blue-800">
        <strong>Note:</strong> This report surfaces evidence only. No hire/no-hire recommendation
        is produced. The hiring committee makes all decisions.
      </div>

      {/* Header */}
      <div>
        <h2 className="text-xl font-semibold text-slate-900">{report.candidate_name}</h2>
        <p className="text-sm text-slate-500 mt-0.5">{report.role_title}</p>
        <div className="mt-2 flex flex-wrap gap-4 text-xs text-slate-500">
          <span>{report.total_debriefs} debrief{report.total_debriefs !== 1 ? 's' : ''}</span>
          <span>{report.total_signals_extracted} signals extracted</span>
          <span>{(report.citation_validity_rate * 100).toFixed(0)}% citation validity</span>
          {report.unsupported_claim_count > 0 && (
            <span className="text-amber-600">{report.unsupported_claim_count} unsupported claims</span>
          )}
          {report.vague_claim_count > 0 && (
            <span className="text-slate-500">{report.vague_claim_count} vague claims</span>
          )}
        </div>
      </div>

      {/* Executive summary */}
      <section>
        <h3 className="text-sm font-semibold text-slate-700 uppercase tracking-wide mb-2">
          Executive Summary
        </h3>
        <p className="text-sm text-slate-700 leading-relaxed whitespace-pre-wrap">
          {report.executive_summary}
        </p>
      </section>

      {/* Competency assessments */}
      <section>
        <h3 className="text-sm font-semibold text-slate-700 uppercase tracking-wide mb-3">
          Competency Assessments
        </h3>
        <div className="space-y-3">
          {report.competency_assessments.map((ca) => {
            const style = STATUS_STYLES[ca.coverage_status] ?? STATUS_STYLES.not_covered;
            return (
              <div key={ca.competency_id} className="border border-slate-200 rounded-lg p-4 bg-white">
                <div className="flex items-center justify-between mb-2">
                  <h4 className="text-sm font-medium text-slate-800">{ca.competency_name}</h4>
                  <span className={`text-xs px-2 py-0.5 rounded border ${style}`}>
                    {ca.coverage_status.replace('_', ' ')}
                  </span>
                </div>
                {ca.synthesis_summary && (
                  <p className="text-sm text-slate-600 mb-2">{ca.synthesis_summary}</p>
                )}
                <div className="flex gap-4 text-xs text-slate-400">
                  <span className="text-emerald-600">{ca.positive_evidence.length} positive signals</span>
                  <span className="text-red-600">{ca.negative_evidence.length} negative signals</span>
                  {ca.vague_claims.length > 0 && (
                    <span className="text-amber-600">{ca.vague_claims.length} vague</span>
                  )}
                </div>
              </div>
            );
          })}
        </div>
      </section>

      {/* Questions for committee */}
      {report.questions_for_committee.length > 0 && (
        <section>
          <h3 className="text-sm font-semibold text-slate-700 uppercase tracking-wide mb-3">
            Questions for the Hiring Committee
          </h3>
          <ul className="space-y-2">
            {report.questions_for_committee.map((q, i) => (
              <li key={i} className="flex gap-3 text-sm text-slate-700">
                <span className="shrink-0 font-medium text-slate-400">{i + 1}.</span>
                <span>{q}</span>
              </li>
            ))}
          </ul>
        </section>
      )}

      {/* Reviewer section */}
      {report.reviewer_approved && (
        <section className="bg-emerald-50 border border-emerald-200 rounded-lg p-4">
          <div className="flex items-center gap-2 mb-2">
            <span className="text-sm font-medium text-emerald-800">Reviewed & Approved</span>
            {report.reviewer_name && (
              <span className="text-xs text-emerald-600">by {report.reviewer_name}</span>
            )}
          </div>
          {report.final_reviewer_notes && (
            <p className="text-sm text-emerald-700">{report.final_reviewer_notes}</p>
          )}
        </section>
      )}
    </div>
  );
}

import type { ExtractedSignal } from '@/lib/types';

const TYPE_STYLES: Record<string, string> = {
  positive: 'bg-emerald-100 text-emerald-800',
  negative: 'bg-red-100 text-red-800',
  mixed: 'bg-amber-100 text-amber-800',
  unclear: 'bg-slate-100 text-slate-700',
};

interface SignalCardProps {
  signal: ExtractedSignal;
  competencyName?: string;
}

export function SignalCard({ signal, competencyName }: SignalCardProps) {
  const typeStyle = TYPE_STYLES[signal.signal_type] ?? TYPE_STYLES.unclear;

  return (
    <div className="border border-slate-200 rounded-lg p-4 bg-white space-y-3">
      <div className="flex items-start justify-between gap-3">
        <div className="space-y-1 flex-1 min-w-0">
          {competencyName && (
            <p className="text-xs font-medium text-slate-500 uppercase tracking-wide">
              {competencyName}
            </p>
          )}
          <p className="text-sm text-slate-800">{signal.claim}</p>
        </div>
        <div className="flex flex-col items-end gap-1 shrink-0">
          <span className={`text-xs font-medium px-2 py-0.5 rounded-full ${typeStyle}`}>
            {signal.signal_type}
          </span>
          <span className="text-xs text-slate-400">
            {Math.round(signal.confidence * 100)}% confidence
          </span>
        </div>
      </div>

      {signal.evidence_spans.length > 0 && (
        <div className="space-y-1.5">
          {signal.evidence_spans.map((span) => (
            <blockquote
              key={span.span_id}
              className="border-l-2 border-slate-300 pl-3 text-xs text-slate-600 italic"
            >
              &ldquo;{span.quoted_text}&rdquo;
              <span className="not-italic ml-2 text-slate-400">— {span.interviewer_name}</span>
            </blockquote>
          ))}
        </div>
      )}

      {(signal.is_vague || signal.is_unsupported) && (
        <div className="flex gap-2">
          {signal.is_vague && (
            <span className="text-xs bg-amber-50 text-amber-700 border border-amber-200 rounded px-2 py-0.5">
              Vague — needs follow-up
            </span>
          )}
          {signal.is_unsupported && (
            <span className="text-xs bg-red-50 text-red-700 border border-red-200 rounded px-2 py-0.5">
              No verifiable evidence span
            </span>
          )}
        </div>
      )}
    </div>
  );
}

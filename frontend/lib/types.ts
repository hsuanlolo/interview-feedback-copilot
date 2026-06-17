/**
 * Frontend TypeScript types mirroring the backend Pydantic schemas.
 * Keep in sync with backend/app/schemas/models.py.
 */

export type SignalType = 'positive' | 'negative' | 'mixed' | 'unclear';
export type DisagreementSeverity = 'high' | 'medium' | 'low';
export type CoverageStatus = 'strong' | 'partial' | 'not_covered' | 'conflicted';

export interface EvidenceSpan {
  span_id: string;
  source_debrief_id: string;
  interviewer_name: string;
  start_char: number;
  end_char: number;
  quoted_text: string;
}

export interface ExtractedSignal {
  signal_id: string;
  debrief_id: string;
  competency_id: string;
  signal_type: SignalType;
  claim: string;
  evidence_spans: EvidenceSpan[];
  confidence: number;
  is_vague: boolean;
  is_unsupported: boolean;
}

export interface DisagreementFlag {
  flag_id: string;
  competency_id: string;
  competency_name: string;
  disagreement_type: string;
  severity: DisagreementSeverity;
  description: string;
  interviewer_names: string[];
  supporting_evidence_spans: EvidenceSpan[];
  resolution_suggestion: string;
}

export interface CoverageGap {
  competency_id: string;
  competency_name: string;
  coverage_status: CoverageStatus;
  interviewers_who_assessed: string[];
  suggested_followup: string;
}

export interface SynthesisReport {
  report_id: string;
  candidate_id: string;
  candidate_name: string;
  role_title: string;
  executive_summary: string;
  disagreement_flags: DisagreementFlag[];
  coverage_gaps: CoverageGap[];
  questions_for_committee: string[];
  total_debriefs: number;
  total_signals_extracted: number;
  unsupported_claim_count: number;
  vague_claim_count: number;
  citation_validity_rate: number;
  final_reviewer_notes: string;
  reviewer_approved: boolean;
  created_at: string;
}

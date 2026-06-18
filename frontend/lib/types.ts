/**
 * Frontend TypeScript types mirroring the backend Pydantic schemas.
 * Keep in sync with backend/app/schemas/models.py.
 */

export type SignalType = 'positive' | 'negative' | 'mixed' | 'unclear';
export type DisagreementSeverity = 'high' | 'medium' | 'low';
export type DisagreementType = 'direction_conflict' | 'score_gap' | 'evidence_absent' | 'score_text_mismatch';
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
  extractor_version: string;
}

export interface Competency {
  competency_id: string;
  name: string;
  description: string;
  required: boolean;
  weight: number;
  positive_indicators: string[];
  negative_indicators: string[];
}

export interface RoleRubric {
  rubric_id: string;
  role_title: string;
  role_level: string;
  department: string;
  competencies: Competency[];
}

export interface InterviewDebrief {
  debrief_id: string;
  candidate_id: string;
  interviewer_name: string;
  round_name: string;
  interview_date: string;
  raw_text: string;
  score_raw: string;
  word_count: number;
}

export interface InterviewerAssessment {
  interviewer_name: string;
  signal_type: SignalType;
  signals: ExtractedSignal[];
  summary: string;
}

export interface CompetencyAssessment {
  competency_id: string;
  competency_name: string;
  coverage_status: CoverageStatus;
  assessments_by_interviewer: InterviewerAssessment[];
  positive_evidence: ExtractedSignal[];
  negative_evidence: ExtractedSignal[];
  vague_claims: ExtractedSignal[];
  synthesis_summary: string;
}

export interface DisagreementFlag {
  flag_id: string;
  competency_id: string;
  competency_name: string;
  disagreement_type: DisagreementType;
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
  role_id: string;
  role_title: string;
  executive_summary: string;
  competency_assessments: CompetencyAssessment[];
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
  reviewer_name: string;
  reviewed_at: string | null;
  created_at: string;
  extractor_version: string;
}

export interface ExtractionResponse {
  signals: ExtractedSignal[];
  total_signals: number;
  extractor_used: string;
  warnings: string[];
}

export interface VerificationResult {
  is_valid: boolean;
  errors: { span_id: string; error_type: string; description: string }[];
  warnings: string[];
  unsupported_claims: string[];
  vague_claims: string[];
  citation_validity_rate: number;
  total_spans_checked: number;
  valid_spans: number;
}

export interface CoverageMapResponse {
  competency_assessments: CompetencyAssessment[];
  coverage_gaps: CoverageGap[];
  overall_coverage_pct: number;
  interviewers: string[];
}

export interface DisagreementsResponse {
  flags: DisagreementFlag[];
  total_flags: number;
  high_severity_count: number;
  medium_severity_count: number;
}

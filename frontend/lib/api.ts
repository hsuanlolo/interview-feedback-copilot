/**
 * Typed API client for the FastAPI backend.
 */

import type {
  CoverageMapResponse,
  DisagreementsResponse,
  ExtractedSignal,
  ExtractionResponse,
  InterviewDebrief,
  RoleRubric,
  SynthesisReport,
  VerificationResult,
} from './types';

const API_BASE = process.env.NEXT_PUBLIC_API_URL ?? 'http://localhost:8000';

async function request<T>(path: string, options?: RequestInit): Promise<T> {
  const res = await fetch(`${API_BASE}${path}`, {
    headers: { 'Content-Type': 'application/json' },
    ...options,
  });
  if (!res.ok) {
    const body = await res.json().catch(() => ({}));
    throw new Error((body as { detail?: string }).detail ?? `Request failed: ${res.status}`);
  }
  return res.json() as Promise<T>;
}

export function checkHealth() {
  return request<{ status: string; version: string; llm_mode: string }>('/health');
}

export function getSampleRubric() {
  return request<RoleRubric>('/rubrics/sample');
}

export function getSampleDebriefs() {
  return request<InterviewDebrief[]>('/debriefs/sample');
}

export function extractBaseline(rubric: RoleRubric, debriefs: InterviewDebrief[]) {
  return request<ExtractionResponse>('/extract/baseline', {
    method: 'POST',
    body: JSON.stringify({ rubric, debriefs }),
  });
}

export function extractLLM(rubric: RoleRubric, debriefs: InterviewDebrief[]) {
  return request<ExtractionResponse>('/extract/llm', {
    method: 'POST',
    body: JSON.stringify({ rubric, debriefs }),
  });
}

export function verifyEvidence(signals: ExtractedSignal[], debriefs: InterviewDebrief[]) {
  return request<VerificationResult>('/verify/evidence', {
    method: 'POST',
    body: JSON.stringify({ signals, debriefs }),
  });
}

export function getCoverageMap(
  signals: ExtractedSignal[],
  rubric: RoleRubric,
  debriefs: InterviewDebrief[],
) {
  return request<CoverageMapResponse>('/analyze/coverage', {
    method: 'POST',
    body: JSON.stringify({ signals, rubric, debriefs }),
  });
}

export function getDisagreements(
  signals: ExtractedSignal[],
  rubric: RoleRubric,
  debriefs: InterviewDebrief[],
) {
  return request<DisagreementsResponse>('/analyze/disagreements', {
    method: 'POST',
    body: JSON.stringify({ signals, rubric, debriefs }),
  });
}

export function synthesize(
  candidateName: string,
  roleTitle: string,
  signals: ExtractedSignal[],
  rubric: RoleRubric,
  debriefs: InterviewDebrief[],
) {
  return request<SynthesisReport>('/synthesize', {
    method: 'POST',
    body: JSON.stringify({
      candidate_name: candidateName,
      role_title: roleTitle,
      signals,
      rubric,
      debriefs,
    }),
  });
}

export function getReport(reportId: string) {
  return request<SynthesisReport>(`/review/${reportId}`);
}

export function updateReview(
  reportId: string,
  notes: string,
  approved: boolean,
  reviewerName: string,
) {
  return request<SynthesisReport>(`/review/${reportId}`, {
    method: 'PATCH',
    body: JSON.stringify({
      final_reviewer_notes: notes,
      reviewer_approved: approved,
      reviewer_name: reviewerName,
    }),
  });
}

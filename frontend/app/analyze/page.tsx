'use client';

import { useState, useEffect } from 'react';
import type {
  CoverageMapResponse,
  DisagreementsResponse,
  ExtractionResponse,
  InterviewDebrief,
  RoleRubric,
  SynthesisReport,
  VerificationResult,
} from '@/lib/types';
import {
  extractBaseline,
  extractLLM,
  getCoverageMap,
  getDisagreements,
  getRubricById,
  getSampleDebriefs,
  listRubrics,
  synthesize,
  updateReview,
  verifyEvidence,
  type RubricMeta,
} from '@/lib/api';
import { SignalCard } from '@/components/SignalCard';
import { CompetencyGrid } from '@/components/CompetencyGrid';
import { DisagreementList } from '@/components/DisagreementList';
import { SynthesisReportViewer } from '@/components/SynthesisReportViewer';

type Step = 'setup' | 'extract' | 'verify' | 'analyze' | 'synthesize' | 'review';

const STEPS: { id: Step; label: string }[] = [
  { id: 'setup', label: '1. Setup' },
  { id: 'extract', label: '2. Extract' },
  { id: 'verify', label: '3. Verify' },
  { id: 'analyze', label: '4. Analyze' },
  { id: 'synthesize', label: '5. Synthesize' },
  { id: 'review', label: '6. Review' },
];

const STEP_ORDER: Step[] = ['setup', 'extract', 'verify', 'analyze', 'synthesize', 'review'];

function StepBar({ current }: { current: Step }) {
  const currentIdx = STEP_ORDER.indexOf(current);
  return (
    <nav className="flex gap-1 overflow-x-auto pb-1">
      {STEPS.map((s, i) => {
        const done = i < currentIdx;
        const active = s.id === current;
        return (
          <div
            key={s.id}
            className={`text-xs px-3 py-1.5 rounded-full whitespace-nowrap ${
              active
                ? 'bg-slate-900 text-white'
                : done
                ? 'bg-emerald-100 text-emerald-700'
                : 'bg-slate-100 text-slate-400'
            }`}
          >
            {s.label}
          </div>
        );
      })}
    </nav>
  );
}

function ErrorAlert({ message }: { message: string }) {
  return (
    <div className="bg-red-50 border border-red-200 rounded-md p-3 text-sm text-red-700">
      {message}
    </div>
  );
}

function Spinner() {
  return (
    <div className="inline-block w-4 h-4 border-2 border-slate-300 border-t-slate-600 rounded-full animate-spin" />
  );
}

export default function AnalyzePage() {
  const [step, setStep] = useState<Step>('setup');
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  // Setup state
  const [candidateName, setCandidateName] = useState('');
  const [roleTitle, setRoleTitle] = useState('');
  const [rubric, setRubric] = useState<RoleRubric | null>(null);
  const [debriefs, setDebriefs] = useState<InterviewDebrief[]>([]);

  // Pipeline state
  const [extractorMode, setExtractorMode] = useState<'baseline' | 'llm'>('baseline');
  const [extraction, setExtraction] = useState<ExtractionResponse | null>(null);
  const [verification, setVerification] = useState<VerificationResult | null>(null);
  const [coverage, setCoverage] = useState<CoverageMapResponse | null>(null);
  const [disagreements, setDisagreements] = useState<DisagreementsResponse | null>(null);
  const [report, setReport] = useState<SynthesisReport | null>(null);

  // Review state
  const [reviewerName, setReviewerName] = useState('');
  const [reviewerNotes, setReviewerNotes] = useState('');
  const [reviewerApproved, setReviewerApproved] = useState(false);
  const [reviewSubmitted, setReviewSubmitted] = useState(false);

  // Add-debrief form state
  const [newInterviewerName, setNewInterviewerName] = useState('');
  const [newDebriefText, setNewDebriefText] = useState('');

  // Rubric picker state
  const [rubricList, setRubricList] = useState<RubricMeta[]>([]);
  const [selectedRubricId, setSelectedRubricId] = useState('');
  const [rubricJson, setRubricJson] = useState('');
  const [rubricJsonError, setRubricJsonError] = useState<string | null>(null);


  useEffect(() => {
    listRubrics()
      .then((list) => {
        setRubricList(list);
        if (list.length > 0) setSelectedRubricId(list[0].rubric_id);
      })
      .catch(() => {
        // non-fatal: user will see empty dropdown and can retry via Load Rubric
      });
  }, []);

  async function handleLoadRubric() {
    if (!selectedRubricId) return;
    setLoading(true);
    setError(null);
    setRubricJsonError(null);
    try {
      const r = await getRubricById(selectedRubricId);
      setRubric(r);
      setRubricJson(JSON.stringify(r, null, 2));
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setLoading(false);
    }
  }

  function handleApplyRubricJson() {
    setRubricJsonError(null);
    try {
      const parsed = JSON.parse(rubricJson) as RoleRubric;
      if (!parsed.role_title || !Array.isArray(parsed.competencies)) {
        setRubricJsonError('Invalid rubric: must have role_title and competencies[]');
        return;
      }
      setRubric(parsed);
    } catch {
      setRubricJsonError('Invalid JSON — check for missing commas or brackets');
    }
  }

  function handleAddDebrief() {
    if (!newInterviewerName.trim() || !newDebriefText.trim()) return;
    const text = newDebriefText.trim();
    const debrief: InterviewDebrief = {
      debrief_id: crypto.randomUUID(),
      candidate_id: candidateName.trim() || 'candidate',
      interviewer_name: newInterviewerName.trim(),
      round_name: '',
      interview_date: new Date().toISOString().split('T')[0],
      raw_text: text,
      score_raw: '',
      word_count: text.split(/\s+/).filter(Boolean).length,
    };
    setDebriefs(prev => [...prev, debrief]);
    setNewInterviewerName('');
    setNewDebriefText('');
  }

  async function handleFileUpload(e: React.ChangeEvent<HTMLInputElement>) {
    const file = e.target.files?.[0];
    if (!file) return;
    e.target.value = '';

    if (file.name.endsWith('.docx')) {
      try {
        const mammoth = await import('mammoth');
        const arrayBuffer = await file.arrayBuffer();
        const result = await mammoth.extractRawText({ arrayBuffer });
        setNewDebriefText(result.value);
      } catch {
        setError('Could not read .docx file. Try saving it as .txt first.');
      }
      return;
    }

    // plain text / markdown
    const reader = new FileReader();
    reader.onload = (ev) => {
      setNewDebriefText((ev.target?.result as string) ?? '');
    };
    reader.readAsText(file);
  }

  function handleRemoveDebrief(id: string) {
    setDebriefs(prev => prev.filter(d => d.debrief_id !== id));
  }

  async function handleLoadSampleData() {
    setLoading(true);
    setError(null);
    try {
      const d = await getSampleDebriefs();
      setDebriefs(d);
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setLoading(false);
    }
  }

  async function handleExtract() {
    if (!rubric || debriefs.length === 0) return;
    setLoading(true);
    setError(null);
    try {
      const result =
        extractorMode === 'baseline'
          ? await extractBaseline(rubric, debriefs)
          : await extractLLM(rubric, debriefs);
      setExtraction(result);
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setLoading(false);
    }
  }

  async function handleVerify() {
    if (!extraction || debriefs.length === 0) return;
    setLoading(true);
    setError(null);
    try {
      const result = await verifyEvidence(extraction.signals, debriefs);
      setVerification(result);
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setLoading(false);
    }
  }

  async function handleAnalyze() {
    if (!extraction || !rubric) return;
    setLoading(true);
    setError(null);
    try {
      const [cov, dis] = await Promise.all([
        getCoverageMap(extraction.signals, rubric, debriefs),
        getDisagreements(extraction.signals, rubric, debriefs),
      ]);
      setCoverage(cov);
      setDisagreements(dis);
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setLoading(false);
    }
  }

  async function handleSynthesize() {
    if (!extraction || !rubric) return;
    setLoading(true);
    setError(null);
    try {
      const result = await synthesize(
        candidateName || 'Candidate',
        roleTitle || rubric.role_title,
        extraction.signals,
        rubric,
        debriefs,
      );
      setReport(result);
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setLoading(false);
    }
  }

  async function handleSubmitReview() {
    if (!report) return;
    setLoading(true);
    setError(null);
    try {
      const updated = await updateReview(
        report.report_id,
        reviewerNotes,
        reviewerApproved,
        reviewerName,
      );
      setReport(updated);
      setReviewSubmitted(true);
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setLoading(false);
    }
  }

  const canProceedFromSetup = rubric !== null && debriefs.length > 0 && candidateName.trim() !== '';
  const canProceedFromExtract = extraction !== null;
  const canProceedFromVerify = verification !== null && verification.is_valid;
  const canProceedFromAnalyze = coverage !== null && disagreements !== null;
  const canProceedFromSynthesize = report !== null;

  return (
    <main className="max-w-4xl mx-auto px-6 py-8 space-y-6">
      <StepBar current={step} />

      <div className="bg-blue-50 border border-blue-200 rounded-md px-4 py-3 text-sm text-blue-800">
        <strong>Reminder:</strong> This tool surfaces evidence only. No hire/no-hire recommendation
        is produced.
      </div>

      {error && <ErrorAlert message={error} />}

      {/* ── Step 1: Setup ─────────────────────────────────────── */}
      {step === 'setup' && (
        <div className="space-y-6">
          <div>
            <h2 className="text-lg font-semibold text-slate-900">Setup</h2>
            <p className="text-sm text-slate-500 mt-1">
              Enter candidate details and load interview data.
            </p>
          </div>

          <div className="grid gap-4 sm:grid-cols-2">
            <div>
              <label className="block text-sm font-medium text-slate-700 mb-1">
                Candidate Name <span className="text-red-500">*</span>
              </label>
              <input
                type="text"
                value={candidateName}
                onChange={(e) => setCandidateName(e.target.value)}
                placeholder="e.g. Jordan Lee"
                className="w-full border border-slate-300 rounded-md px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-slate-400"
              />
            </div>
            <div>
              <label className="block text-sm font-medium text-slate-700 mb-1">
                Role Title
              </label>
              <input
                type="text"
                value={roleTitle}
                onChange={(e) => setRoleTitle(e.target.value)}
                placeholder="Loaded from rubric if blank"
                className="w-full border border-slate-300 rounded-md px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-slate-400"
              />
            </div>
          </div>

          {/* ── Step 1A: Pick a Rubric ──────────────────────────── */}
          <div className="border border-slate-200 rounded-lg p-4 bg-white space-y-4">
            <div>
              <h3 className="text-sm font-medium text-slate-800">Step 1 — Choose a Rubric</h3>
              <p className="text-xs text-slate-500 mt-0.5">
                Pick a built-in role rubric, then edit the JSON to match your team's qualifications.
              </p>
            </div>

            <div className="flex gap-2">
              <select
                value={selectedRubricId}
                onChange={(e) => setSelectedRubricId(e.target.value)}
                className="flex-1 border border-slate-300 rounded-md px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-slate-400 bg-white"
              >
                {rubricList.length === 0 && (
                  <option value="">— loading roles… —</option>
                )}
                {rubricList.map((r) => (
                  <option key={r.rubric_id} value={r.rubric_id}>
                    {r.role_title} · {r.role_level}
                  </option>
                ))}
              </select>
              <button
                onClick={handleLoadRubric}
                disabled={loading || !selectedRubricId}
                className="flex items-center gap-2 px-4 py-2 bg-slate-900 text-white text-sm rounded-lg hover:bg-slate-700 disabled:opacity-40 transition-colors whitespace-nowrap"
              >
                {loading && <Spinner />}
                Load Rubric
              </button>
            </div>

            {rubricJson && (
              <div className="space-y-2">
                <div className="flex items-center justify-between">
                  <label className="text-xs font-medium text-slate-700">
                    Rubric JSON — edit to customize competencies and indicators
                  </label>
                  <button
                    onClick={handleApplyRubricJson}
                    className="text-xs px-3 py-1 bg-emerald-700 text-white rounded-md hover:bg-emerald-800 transition-colors"
                  >
                    Apply Changes
                  </button>
                </div>
                <textarea
                  value={rubricJson}
                  onChange={(e) => { setRubricJson(e.target.value); setRubricJsonError(null); }}
                  rows={14}
                  spellCheck={false}
                  className="w-full border border-slate-300 rounded-md px-3 py-2 text-xs font-mono focus:outline-none focus:ring-2 focus:ring-slate-400 resize-y"
                />
                {rubricJsonError && (
                  <p className="text-xs text-red-600">{rubricJsonError}</p>
                )}
                {rubric && !rubricJsonError && (
                  <p className="text-xs text-emerald-600">
                    ✓ Active: {rubric.role_title} — {rubric.competencies.length} competencies
                  </p>
                )}
              </div>
            )}
          </div>

          {/* ── Also load sample debriefs (optional) ────────────── */}
          <div className="border border-slate-200 rounded-lg p-4 bg-white">
            <div className="flex items-center justify-between">
              <div>
                <h3 className="text-sm font-medium text-slate-800">Load Sample Debriefs (optional)</h3>
                <p className="text-xs text-slate-500 mt-0.5">
                  Loads 3 synthetic debriefs to test the pipeline end-to-end.
                </p>
              </div>
              <button
                onClick={handleLoadSampleData}
                disabled={loading}
                className="flex items-center gap-2 px-4 py-2 border border-slate-300 text-slate-700 text-sm rounded-lg hover:bg-slate-50 disabled:opacity-50 transition-colors whitespace-nowrap"
              >
                {loading && <Spinner />}
                Load Sample Debriefs
              </button>
            </div>
          </div>

          {/* ── Option B: Add Your Own Debriefs ─────────────────── */}
          <div className="border border-slate-200 rounded-lg p-4 bg-white space-y-4">
            <div>
              <h3 className="text-sm font-medium text-slate-800">Option B — Add Your Own Debriefs</h3>
              <p className="text-xs text-slate-500 mt-0.5">
                Paste text or upload a .txt / .docx file for each interviewer. Add one at a time.
              </p>
            </div>

            <div className="space-y-3">
              <div>
                <label className="block text-xs font-medium text-slate-700 mb-1">Interviewer Name</label>
                <input
                  type="text"
                  value={newInterviewerName}
                  onChange={(e) => setNewInterviewerName(e.target.value)}
                  placeholder="e.g. Sarah Chen"
                  className="w-full border border-slate-300 rounded-md px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-slate-400"
                />
              </div>

              <div>
                <label className="block text-xs font-medium text-slate-700 mb-1">Debrief Text</label>
                <textarea
                  value={newDebriefText}
                  onChange={(e) => setNewDebriefText(e.target.value)}
                  placeholder="Paste the debrief notes here..."
                  rows={5}
                  className="w-full border border-slate-300 rounded-md px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-slate-400 resize-y font-mono"
                />
              </div>

              <div className="flex items-center gap-2 flex-wrap">
                <label className="cursor-pointer flex items-center gap-1.5 px-3 py-1.5 border border-slate-300 text-slate-700 text-xs rounded-lg hover:bg-slate-50 transition-colors">
                  <svg xmlns="http://www.w3.org/2000/svg" className="h-3.5 w-3.5" viewBox="0 0 20 20" fill="currentColor">
                    <path fillRule="evenodd" d="M3 17a1 1 0 011-1h12a1 1 0 110 2H4a1 1 0 01-1-1zM6.293 6.707a1 1 0 010-1.414l3-3a1 1 0 011.414 0l3 3a1 1 0 01-1.414 1.414L11 5.414V13a1 1 0 11-2 0V5.414L7.707 6.707a1 1 0 01-1.414 0z" clipRule="evenodd" />
                  </svg>
                  Upload .txt or .docx
                  <input type="file" accept=".txt,.md,.docx" onChange={handleFileUpload} className="hidden" />
                </label>
                <span className="text-slate-300 text-xs">— or paste text above</span>
                <div className="flex-1" />
                <button
                  onClick={handleAddDebrief}
                  disabled={!newInterviewerName.trim() || !newDebriefText.trim()}
                  className="px-4 py-1.5 bg-slate-800 text-white text-xs rounded-lg hover:bg-slate-700 disabled:opacity-40 transition-colors"
                >
                  Add Debrief
                </button>
              </div>
            </div>

            {debriefs.length > 0 && (
              <div className="space-y-2 pt-1 border-t border-slate-100">
                <p className="text-xs text-slate-500 font-medium">Added debriefs ({debriefs.length})</p>
                {debriefs.map((d) => (
                  <div key={d.debrief_id} className="flex items-center justify-between bg-slate-50 rounded-md px-3 py-2">
                    <div>
                      <span className="text-xs font-medium text-slate-700">{d.interviewer_name}</span>
                      <span className="text-xs text-slate-400 ml-2">
                        {d.raw_text.length.toLocaleString()} chars
                      </span>
                    </div>
                    <button
                      onClick={() => handleRemoveDebrief(d.debrief_id)}
                      className="text-xs text-red-400 hover:text-red-600"
                    >
                      Remove
                    </button>
                  </div>
                ))}
              </div>
            )}

            {!rubric && (
              <div className="pt-1 border-t border-slate-100">
                <p className="text-xs text-slate-500">
                  Rubric required — use <span className="font-medium text-slate-700">Step 1</span> above to choose and load one.
                </p>
              </div>
            )}
          </div>

          <div className="flex justify-end">
            <button
              onClick={() => setStep('extract')}
              disabled={!canProceedFromSetup}
              className="px-5 py-2 bg-slate-900 text-white text-sm rounded-lg hover:bg-slate-700 disabled:opacity-40 transition-colors"
            >
              Next: Extract Signals →
            </button>
          </div>
        </div>
      )}

      {/* ── Step 2: Extract ───────────────────────────────────── */}
      {step === 'extract' && (
        <div className="space-y-6">
          <div>
            <h2 className="text-lg font-semibold text-slate-900">Signal Extraction</h2>
            <p className="text-sm text-slate-500 mt-1">
              Extract structured signals from debrief text, grounded in verbatim quotes.
            </p>
          </div>

          <div className="border border-slate-200 rounded-lg p-4 bg-white space-y-4">
            <div>
              <p className="text-sm font-medium text-slate-700 mb-2">Extractor</p>
              <div className="flex gap-4">
                <label className="flex items-center gap-2 text-sm text-slate-700 cursor-pointer">
                  <input
                    type="radio"
                    value="baseline"
                    checked={extractorMode === 'baseline'}
                    onChange={() => setExtractorMode('baseline')}
                    className="text-slate-900"
                  />
                  Baseline (keyword matching, fully deterministic)
                </label>
                <label className="flex items-center gap-2 text-sm text-slate-700 cursor-pointer">
                  <input
                    type="radio"
                    value="llm"
                    checked={extractorMode === 'llm'}
                    onChange={() => setExtractorMode('llm')}
                    className="text-slate-900"
                  />
                  LLM (Claude tool_use, requires API key)
                </label>
              </div>
            </div>

            <div className="flex items-center justify-between">
              <p className="text-xs text-slate-400">
                Running against {debriefs.length} debrief{debriefs.length !== 1 ? 's' : ''} from{' '}
                {debriefs.map((d) => d.interviewer_name).join(', ')}
              </p>
              <button
                onClick={handleExtract}
                disabled={loading}
                className="flex items-center gap-2 px-4 py-2 bg-slate-900 text-white text-sm rounded-lg hover:bg-slate-700 disabled:opacity-50 transition-colors"
              >
                {loading && <Spinner />}
                Run Extraction
              </button>
            </div>
          </div>

          {extraction && (
            <div className="space-y-3">
              <div className="flex items-center gap-4 text-sm">
                <span className="font-medium text-slate-700">
                  {extraction.total_signals} signals extracted
                </span>
                <span className="text-slate-400">via {extraction.extractor_used}</span>
              </div>

              {extraction.warnings.length > 0 && (
                <div className="bg-amber-50 border border-amber-200 rounded-md p-3 text-sm text-amber-800">
                  <strong>Warnings:</strong>
                  <ul className="mt-1 list-disc list-inside space-y-0.5">
                    {extraction.warnings.map((w, i) => <li key={i}>{w}</li>)}
                  </ul>
                </div>
              )}

              <div className="space-y-2">
                {extraction.signals.slice(0, 10).map((s) => (
                  <SignalCard key={s.signal_id} signal={s} />
                ))}
                {extraction.signals.length > 10 && (
                  <p className="text-xs text-slate-400 text-center">
                    + {extraction.signals.length - 10} more signals
                  </p>
                )}
              </div>
            </div>
          )}

          <div className="flex justify-between">
            <button
              onClick={() => setStep('setup')}
              className="px-4 py-2 text-sm text-slate-600 hover:text-slate-900"
            >
              ← Back
            </button>
            <button
              onClick={() => setStep('verify')}
              disabled={!canProceedFromExtract}
              className="px-5 py-2 bg-slate-900 text-white text-sm rounded-lg hover:bg-slate-700 disabled:opacity-40 transition-colors"
            >
              Next: Verify Evidence →
            </button>
          </div>
        </div>
      )}

      {/* ── Step 3: Verify ────────────────────────────────────── */}
      {step === 'verify' && (
        <div className="space-y-6">
          <div>
            <h2 className="text-lg font-semibold text-slate-900">Evidence Verification</h2>
            <p className="text-sm text-slate-500 mt-1">
              Every evidence span is checked against the original debrief text.
              100% citation validity is required to proceed.
            </p>
          </div>

          <div className="border border-slate-200 rounded-lg p-4 bg-white">
            <div className="flex items-center justify-between">
              <p className="text-sm text-slate-600">
                Checking {extraction?.signals.length ?? 0} signals across {debriefs.length} debriefs
              </p>
              <button
                onClick={handleVerify}
                disabled={loading}
                className="flex items-center gap-2 px-4 py-2 bg-slate-900 text-white text-sm rounded-lg hover:bg-slate-700 disabled:opacity-50 transition-colors"
              >
                {loading && <Spinner />}
                Verify Evidence
              </button>
            </div>
          </div>

          {verification && (
            <div className="space-y-3">
              <div
                className={`rounded-lg p-4 border ${
                  verification.is_valid
                    ? 'bg-emerald-50 border-emerald-200'
                    : 'bg-red-50 border-red-200'
                }`}
              >
                <p
                  className={`text-sm font-medium ${
                    verification.is_valid ? 'text-emerald-800' : 'text-red-800'
                  }`}
                >
                  {verification.is_valid
                    ? '✓ All evidence spans verified'
                    : '✗ Verification failed — some spans could not be located'}
                </p>
                <div className="mt-2 flex flex-wrap gap-4 text-xs text-slate-500">
                  <span>{verification.total_spans_checked} spans checked</span>
                  <span>{verification.valid_spans} valid</span>
                  <span>
                    {(verification.citation_validity_rate * 100).toFixed(0)}% citation validity rate
                  </span>
                </div>
              </div>

              {verification.errors.length > 0 && (
                <div className="space-y-2">
                  <h4 className="text-sm font-medium text-red-700">Span Errors</h4>
                  {verification.errors.map((e) => (
                    <div
                      key={e.span_id}
                      className="bg-red-50 border border-red-200 rounded-md p-3 text-xs text-red-700"
                    >
                      <strong>{e.error_type}</strong>: {e.description}
                    </div>
                  ))}
                </div>
              )}

              {verification.warnings.length > 0 && (
                <div className="bg-amber-50 border border-amber-200 rounded-md p-3 text-sm text-amber-800">
                  <strong>Warnings:</strong>
                  <ul className="mt-1 list-disc list-inside space-y-0.5 text-xs">
                    {verification.warnings.map((w, i) => <li key={i}>{w}</li>)}
                  </ul>
                </div>
              )}

              {!verification.is_valid && (
                <div className="bg-slate-50 border border-slate-200 rounded-md p-3 text-sm text-slate-600">
                  Verification failed. Go back to extraction and try the baseline extractor,
                  or check that the debrief text matches what was extracted.
                </div>
              )}
            </div>
          )}

          <div className="flex justify-between">
            <button
              onClick={() => setStep('extract')}
              className="px-4 py-2 text-sm text-slate-600 hover:text-slate-900"
            >
              ← Back
            </button>
            <button
              onClick={() => setStep('analyze')}
              disabled={!canProceedFromVerify}
              className="px-5 py-2 bg-slate-900 text-white text-sm rounded-lg hover:bg-slate-700 disabled:opacity-40 transition-colors"
            >
              Next: Analyze Coverage →
            </button>
          </div>
        </div>
      )}

      {/* ── Step 4: Analyze ───────────────────────────────────── */}
      {step === 'analyze' && (
        <div className="space-y-6">
          <div>
            <h2 className="text-lg font-semibold text-slate-900">Coverage & Disagreements</h2>
            <p className="text-sm text-slate-500 mt-1">
              Assess which competencies were covered by which interviewers, and flag conflicts.
            </p>
          </div>

          <div className="border border-slate-200 rounded-lg p-4 bg-white">
            <div className="flex items-center justify-between">
              <p className="text-sm text-slate-600">
                Analyzing {rubric?.competencies.length ?? 0} competencies across{' '}
                {debriefs.length} debriefs
              </p>
              <button
                onClick={handleAnalyze}
                disabled={loading}
                className="flex items-center gap-2 px-4 py-2 bg-slate-900 text-white text-sm rounded-lg hover:bg-slate-700 disabled:opacity-50 transition-colors"
              >
                {loading && <Spinner />}
                Run Analysis
              </button>
            </div>
          </div>

          {coverage && (
            <div className="space-y-2">
              <h3 className="text-sm font-medium text-slate-700">Coverage Map</h3>
              <CompetencyGrid coverage={coverage} />
            </div>
          )}

          {disagreements && (
            <div className="space-y-2">
              <h3 className="text-sm font-medium text-slate-700">Disagreements</h3>
              <DisagreementList disagreements={disagreements} />
            </div>
          )}

          <div className="flex justify-between">
            <button
              onClick={() => setStep('verify')}
              className="px-4 py-2 text-sm text-slate-600 hover:text-slate-900"
            >
              ← Back
            </button>
            <button
              onClick={() => setStep('synthesize')}
              disabled={!canProceedFromAnalyze}
              className="px-5 py-2 bg-slate-900 text-white text-sm rounded-lg hover:bg-slate-700 disabled:opacity-40 transition-colors"
            >
              Next: Synthesize Report →
            </button>
          </div>
        </div>
      )}

      {/* ── Step 5: Synthesize ────────────────────────────────── */}
      {step === 'synthesize' && (
        <div className="space-y-6">
          <div>
            <h2 className="text-lg font-semibold text-slate-900">Synthesis Report</h2>
            <p className="text-sm text-slate-500 mt-1">
              Generate a structured, evidence-grounded report for the hiring committee.
              No recommendation will be produced.
            </p>
          </div>

          <div className="border border-slate-200 rounded-lg p-4 bg-white">
            <div className="flex items-center justify-between">
              <p className="text-sm text-slate-600">
                Synthesizing {extraction?.total_signals ?? 0} signals for{' '}
                <strong>{candidateName}</strong>
              </p>
              <button
                onClick={handleSynthesize}
                disabled={loading || report !== null}
                className="flex items-center gap-2 px-4 py-2 bg-slate-900 text-white text-sm rounded-lg hover:bg-slate-700 disabled:opacity-50 transition-colors"
              >
                {loading && <Spinner />}
                {report ? 'Report Generated' : 'Generate Report'}
              </button>
            </div>
          </div>

          {report && <SynthesisReportViewer report={report} />}

          <div className="flex justify-between">
            <button
              onClick={() => setStep('analyze')}
              className="px-4 py-2 text-sm text-slate-600 hover:text-slate-900"
            >
              ← Back
            </button>
            <button
              onClick={() => setStep('review')}
              disabled={!canProceedFromSynthesize}
              className="px-5 py-2 bg-slate-900 text-white text-sm rounded-lg hover:bg-slate-700 disabled:opacity-40 transition-colors"
            >
              Next: Human Review →
            </button>
          </div>
        </div>
      )}

      {/* ── Step 6: Review ───────────────────────────────────── */}
      {step === 'review' && (
        <div className="space-y-6">
          <div>
            <h2 className="text-lg font-semibold text-slate-900">Human Review</h2>
            <p className="text-sm text-slate-500 mt-1">
              A human reviewer must add notes and approve before the report is shared.
              This step is required, not optional.
            </p>
          </div>

          {reviewSubmitted ? (
            <div className="bg-emerald-50 border border-emerald-200 rounded-lg p-6 text-center space-y-2">
              <p className="text-lg font-medium text-emerald-800">
                {reviewerApproved ? 'Report Approved' : 'Notes Saved'}
              </p>
              <p className="text-sm text-emerald-600">
                Reviewer: {reviewerName || '(unnamed)'}
              </p>
              {report?.report_id && (
                <p className="text-xs text-slate-500 font-mono mt-2">
                  Report ID: {report.report_id}
                </p>
              )}
            </div>
          ) : (
            <div className="border border-slate-200 rounded-lg p-5 bg-white space-y-4">
              <div>
                <label className="block text-sm font-medium text-slate-700 mb-1">
                  Reviewer Name
                </label>
                <input
                  type="text"
                  value={reviewerName}
                  onChange={(e) => setReviewerName(e.target.value)}
                  placeholder="Your name"
                  className="w-full border border-slate-300 rounded-md px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-slate-400"
                />
              </div>

              <div>
                <label className="block text-sm font-medium text-slate-700 mb-1">
                  Reviewer Notes
                </label>
                <textarea
                  value={reviewerNotes}
                  onChange={(e) => setReviewerNotes(e.target.value)}
                  placeholder="Add observations, corrections, or context for the hiring committee..."
                  rows={4}
                  className="w-full border border-slate-300 rounded-md px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-slate-400 resize-none"
                />
              </div>

              <label className="flex items-start gap-3 cursor-pointer">
                <input
                  type="checkbox"
                  checked={reviewerApproved}
                  onChange={(e) => setReviewerApproved(e.target.checked)}
                  className="mt-0.5"
                />
                <span className="text-sm text-slate-700">
                  I confirm that I have reviewed this report and it is ready to share with the
                  hiring committee. I understand that no hire/no-hire recommendation is made —
                  the committee will make that decision.
                </span>
              </label>

              <div className="flex justify-end">
                <button
                  onClick={handleSubmitReview}
                  disabled={loading || !reviewerName.trim()}
                  className="flex items-center gap-2 px-5 py-2 bg-slate-900 text-white text-sm rounded-lg hover:bg-slate-700 disabled:opacity-40 transition-colors"
                >
                  {loading && <Spinner />}
                  Submit Review
                </button>
              </div>
            </div>
          )}

          {report && (
            <div className="border-t border-slate-200 pt-4">
              <h3 className="text-sm font-medium text-slate-700 mb-3">Report Preview</h3>
              <SynthesisReportViewer report={report} />
            </div>
          )}

          <div className="flex justify-start">
            <button
              onClick={() => setStep('synthesize')}
              className="px-4 py-2 text-sm text-slate-600 hover:text-slate-900"
            >
              ← Back
            </button>
          </div>
        </div>
      )}
    </main>
  );
}

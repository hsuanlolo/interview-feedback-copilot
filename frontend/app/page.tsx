import Link from 'next/link';

const CONSTRAINTS = [
  'No hire/no-hire recommendation — the tool surfaces evidence, humans decide',
  'Every model-generated claim cites a verbatim source span from the debrief',
  'Pydantic validation gates all LLM output — invalid output is rejected, not silently accepted',
  'Human review is a required step, not an optional add-on',
];

const PIPELINE_STEPS = [
  { label: 'Extract', description: 'Baseline keyword matching or Claude tool_use' },
  { label: 'Verify', description: '100% citation validity gate — every span is checked' },
  { label: 'Analyze', description: 'Coverage map + disagreement detection across interviewers' },
  { label: 'Synthesize', description: 'Evidence-grounded report, no recommendation language' },
  { label: 'Review', description: 'Human reviewer adds notes and approves before sharing' },
];

export default function HomePage() {
  return (
    <main className="max-w-4xl mx-auto px-6 py-12 space-y-12">
      {/* Hero */}
      <div className="space-y-4">
        <h1 className="text-3xl font-semibold text-slate-900">
          Evidence-Grounded Interview Feedback Copilot
        </h1>
        <p className="text-lg text-slate-600 max-w-2xl">
          Surfaces what interviewers actually said, organized by competency.
          Every claim is grounded in verbatim text from the original debrief.
          No recommendation is ever produced — that stays with the hiring committee.
        </p>
        <div className="flex gap-3">
          <Link
            href="/analyze"
            className="inline-flex items-center px-5 py-2.5 bg-slate-900 text-white text-sm font-medium rounded-lg hover:bg-slate-700 transition-colors"
          >
            Run an Analysis
          </Link>
          <a
            href="http://localhost:8000/docs"
            target="_blank"
            rel="noreferrer"
            className="inline-flex items-center px-5 py-2.5 border border-slate-300 text-sm font-medium rounded-lg text-slate-700 hover:bg-slate-100 transition-colors"
          >
            API Docs
          </a>
        </div>
      </div>

      {/* Pipeline overview */}
      <section className="space-y-4">
        <h2 className="text-sm font-semibold text-slate-500 uppercase tracking-wide">
          Analysis Pipeline
        </h2>
        <div className="grid gap-3 sm:grid-cols-5">
          {PIPELINE_STEPS.map((step, i) => (
            <div key={step.label} className="relative">
              <div className="bg-white border border-slate-200 rounded-lg p-4 h-full">
                <div className="text-xs font-medium text-slate-400 mb-1">Step {i + 1}</div>
                <div className="text-sm font-semibold text-slate-800 mb-1">{step.label}</div>
                <div className="text-xs text-slate-500">{step.description}</div>
              </div>
            </div>
          ))}
        </div>
      </section>

      {/* Design constraints */}
      <section className="space-y-4">
        <h2 className="text-sm font-semibold text-slate-500 uppercase tracking-wide">
          Non-Negotiable Design Constraints
        </h2>
        <ul className="space-y-2">
          {CONSTRAINTS.map((c) => (
            <li key={c} className="flex gap-3 text-sm text-slate-700">
              <span className="text-emerald-500 shrink-0 mt-0.5">✓</span>
              <span>{c}</span>
            </li>
          ))}
        </ul>
      </section>

      {/* Tech stack */}
      <section className="space-y-3">
        <h2 className="text-sm font-semibold text-slate-500 uppercase tracking-wide">
          Tech Stack
        </h2>
        <div className="flex flex-wrap gap-2">
          {[
            'FastAPI', 'Pydantic v2', 'Python 3.11', 'Claude tool_use',
            'Next.js 14', 'TypeScript', 'Tailwind CSS',
          ].map((tech) => (
            <span
              key={tech}
              className="text-xs bg-white border border-slate-200 rounded px-2.5 py-1 text-slate-600"
            >
              {tech}
            </span>
          ))}
        </div>
      </section>
    </main>
  );
}

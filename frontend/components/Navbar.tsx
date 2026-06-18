import Link from 'next/link';

export function Navbar() {
  return (
    <nav className="bg-white border-b border-slate-200">
      <div className="max-w-6xl mx-auto px-6 py-4 flex items-center justify-between">
        <Link href="/" className="font-semibold text-slate-900 hover:text-slate-700">
          Interview Feedback Copilot
        </Link>
        <div className="flex items-center gap-6 text-sm text-slate-600">
          <Link href="/analyze" className="hover:text-slate-900">
            New Analysis
          </Link>
          <a
            href="http://localhost:8000/docs"
            target="_blank"
            rel="noreferrer"
            className="hover:text-slate-900"
          >
            API Docs
          </a>
        </div>
      </div>
    </nav>
  );
}

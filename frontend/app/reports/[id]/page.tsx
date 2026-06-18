import { getReport } from '@/lib/api';
import { SynthesisReportViewer } from '@/components/SynthesisReportViewer';
import Link from 'next/link';

interface Props {
  params: { id: string };
}

export default async function ReportPage({ params }: Props) {
  let report;
  try {
    report = await getReport(params.id);
  } catch {
    return (
      <main className="max-w-3xl mx-auto px-6 py-12 text-center space-y-4">
        <h1 className="text-xl font-semibold text-slate-900">Report Not Found</h1>
        <p className="text-sm text-slate-500">
          Report <code className="font-mono bg-slate-100 px-1 rounded">{params.id}</code> could
          not be found. Reports are stored in memory and are lost when the server restarts.
        </p>
        <Link href="/analyze" className="inline-block text-sm text-slate-700 hover:text-slate-900 underline">
          Start a new analysis
        </Link>
      </main>
    );
  }

  return (
    <main className="max-w-3xl mx-auto px-6 py-10 space-y-6">
      <div className="flex items-center justify-between">
        <div>
          <p className="text-xs text-slate-400 font-mono">{report.report_id}</p>
          <h1 className="text-xl font-semibold text-slate-900 mt-0.5">{report.candidate_name}</h1>
          <p className="text-sm text-slate-500">{report.role_title}</p>
        </div>
        <Link
          href="/analyze"
          className="text-sm text-slate-600 hover:text-slate-900 border border-slate-200 rounded-lg px-3 py-1.5"
        >
          New Analysis
        </Link>
      </div>

      <SynthesisReportViewer report={report} />
    </main>
  );
}

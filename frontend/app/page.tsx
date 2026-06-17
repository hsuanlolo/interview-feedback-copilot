/**
 * Home page — placeholder until PROMPT 11 (Frontend MVP).
 * Shows project status and links to the API docs.
 */
export default function HomePage() {
  return (
    <main className="min-h-screen flex items-center justify-center p-8">
      <div className="max-w-xl w-full space-y-6">
        <div>
          <h1 className="text-2xl font-semibold text-slate-900">
            Interview Feedback Copilot
          </h1>
          <p className="mt-1 text-sm text-slate-500">
            Evidence-grounded synthesis. Surfaces evidence. Human decides.
          </p>
        </div>

        <div className="bg-amber-50 border border-amber-200 rounded-md p-4 text-sm text-amber-800">
          <strong>Status:</strong> Under construction. Frontend UI will be built in Milestone 11.
        </div>

        <div className="space-y-2 text-sm">
          <p className="font-medium text-slate-700">Available now:</p>
          <ul className="list-disc list-inside space-y-1 text-slate-600">
            <li>
              <a
                href="http://localhost:8000/docs"
                className="text-blue-600 hover:underline"
                target="_blank"
                rel="noreferrer"
              >
                Backend API docs (Swagger UI)
              </a>
            </li>
            <li>
              <a
                href="http://localhost:8000/health"
                className="text-blue-600 hover:underline"
                target="_blank"
                rel="noreferrer"
              >
                Health check endpoint
              </a>
            </li>
          </ul>
        </div>

        <div className="space-y-2 text-sm">
          <p className="font-medium text-slate-700">Design constraints:</p>
          <ul className="list-disc list-inside space-y-1 text-slate-600">
            <li>No hire/no-hire recommendation — human decides</li>
            <li>Every claim cites a source span from the debrief</li>
            <li>Human review is a required step</li>
          </ul>
        </div>
      </div>
    </main>
  );
}

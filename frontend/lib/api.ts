/**
 * Typed API client for the FastAPI backend.
 * All backend types are mirrored here so the frontend has end-to-end type safety.
 * Expanded in PROMPT 11.
 */

const API_BASE = process.env.NEXT_PUBLIC_API_URL ?? 'http://localhost:8000';

export async function checkHealth(): Promise<{ status: string; version: string; llm_mode: string }> {
  const res = await fetch(`${API_BASE}/health`);
  if (!res.ok) throw new Error(`Health check failed: ${res.status}`);
  return res.json();
}

// Additional typed API functions will be added alongside each backend endpoint.

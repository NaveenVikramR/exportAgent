const API_URL = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";

export type Health = {
  status: string;
  database: string;
  nebius_configured: boolean;
  tavily_configured: boolean;
};

export type Route = {
  task_type: string;
  tier: string;
  model: string;
};

export type LLMCall = {
  id: number;
  run_id: number | null;
  task_type: string;
  tier: string;
  model: string;
  input_tokens: number;
  output_tokens: number;
  latency_ms: number;
  cost_usd: string;
  success: boolean;
  error: string | null;
  created_at: string;
};

export type ModelUsage = {
  model: string;
  tier: string;
  calls: number;
  input_tokens: number;
  output_tokens: number;
  avg_latency_ms: number;
  cost_usd: string;
};

export type TraceSummary = {
  total_calls: number;
  total_cost_usd: string;
  by_model: ModelUsage[];
};

async function get<T>(path: string): Promise<T> {
  const response = await fetch(`${API_URL}/api${path}`, { cache: "no-store" });
  if (!response.ok) {
    throw new Error(`API ${path} returned ${response.status}`);
  }
  return response.json() as Promise<T>;
}

export const api = {
  health: () => get<Health>("/health"),
  routes: () => get<Route[]>("/trace/routes"),
  calls: (limit = 20) => get<LLMCall[]>(`/trace/calls?limit=${limit}`),
  summary: () => get<TraceSummary>("/trace/summary"),
};

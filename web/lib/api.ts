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
  source: string;
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
  llm_mode: string;
  spent_today_usd: string;
  daily_spend_cap_usd: string;
  by_model: ModelUsage[];
};

export type Extracted = {
  value: string | number | null;
  confidence: number;
  evidence: string | null;
};

export type LineItem = {
  colour: string | null;
  sizes: Record<string, number>;
  quantity: number | null;
  unit_price: string | null;
};

export type ReviewFlag = {
  field: string;
  reason: string;
  detail: string;
};

export type Classification = {
  category: string;
  intents: string[];
  has_po_data: boolean;
  summary: string;
  confidence: number;
};

export type ScalarField =
  | "buyer"
  | "po_number"
  | "style"
  | "currency"
  | "unit_price"
  | "total_quantity"
  | "delivery_date"
  | "incoterms"
  | "port"
  | "destination_country";

export type Extraction = {
  fields: Record<ScalarField, Extracted> & { line_items: LineItem[] };
  review: ReviewFlag[];
};

export type EmailSummary = {
  id: number;
  external_id: string | null;
  sender: string;
  subject: string;
  received_at: string;
  status: string;
  classification: Classification | null;
  review_count: number;
};

export type EmailDetail = EmailSummary & {
  body: string;
  attachments: { id: number; filename: string; content_type: string; text_content: string | null }[];
  extraction: Extraction | null;
  analysis_error: string | null;
  notice: string | null;
};

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const response = await fetch(`${API_URL}/api${path}`, { cache: "no-store", ...init });
  if (!response.ok) {
    const body = await response.json().catch(() => null);
    throw new Error(body?.detail ?? `The server returned ${response.status}.`);
  }
  return response.json() as Promise<T>;
}

function get<T>(path: string): Promise<T> {
  return request<T>(path);
}

export const api = {
  health: () => get<Health>("/health"),
  routes: () => get<Route[]>("/trace/routes"),
  calls: (limit = 20) => get<LLMCall[]>(`/trace/calls?limit=${limit}`),
  summary: () => get<TraceSummary>("/trace/summary"),
  emails: () => get<EmailSummary[]>("/emails"),
  email: (id: string) => get<EmailDetail>(`/emails/${id}`),
  analyse: (id: string, force: boolean) =>
    request<EmailDetail>(`/emails/${id}/analyse?force=${force}`, { method: "POST" }),
};

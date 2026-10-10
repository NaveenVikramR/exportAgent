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
  detail: string | null;
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

export type Escalation = {
  field: string;
  reason: string;
  model: string;
  calls: number;
  input_tokens: number;
  output_tokens: number;
  cost_usd: string;
  outcome: "resolved" | "unresolved" | "failed" | "skipped_spend_cap";
  before: unknown;
  after: unknown;
};

export type Extraction = {
  fields: Record<ScalarField, Extracted> & { line_items: LineItem[] };
  review: ReviewFlag[];
  escalations: Escalation[];
};

export type RiskFlag = {
  severity: "high" | "medium" | "low";
  category: string;
  reason: string;
  evidence: string[];
  rule: string | null;
  adverse_finding: string | null;
  verified: boolean;
  source: "model" | "rule";
  severity_adjusted_from: "high" | "medium" | "low" | null;
};

export type InfoItem = {
  topic: string;
  finding: string;
  evidence: string[];
  note: string | null;
};

export type Draft = {
  id: number;
  email_id: number;
  order_id: number | null;
  kind: "buyer_reply" | "internal_note";
  subject: string | null;
  body: string;
  edited_body: string | null;
  text: string;
  status: "pending" | "sent" | "rejected" | "superseded";
  checked: number;
  violations: { kind: string; text: string; detail: string }[];
  reviewed_by: string | null;
  reviewed_at: string | null;
  sent_at: string | null;
  reject_reason: string | null;
  created_at: string;
  model: string | null;
  cost_usd: string | null;
  email_subject: string | null;
  email_sender: string | null;
};

export type AgentStep = {
  id: number;
  seq: number;
  round: number;
  kind: "llm" | "tool";
  name: string;
  input: Record<string, unknown> | null;
  output: Record<string, unknown> | null;
  summary: string | null;
  evidence_id: string | null;
  model: string | null;
  tier: string | null;
  input_tokens: number | null;
  output_tokens: number | null;
  latency_ms: number | null;
  cost_usd: string | null;
  call_source: string | null;
};

export type AgentRun = {
  id: number;
  status: string;
  rounds: number;
  result: { summary: string; flags: RiskFlag[]; info_checked: InfoItem[] } | null;
  error: string | null;
  started_at: string;
  finished_at: string | null;
  steps: AgentStep[];
  ultra_calls: number;
  total_cost_usd: string;
  notice: string | null;
};

export type EmailSummary = {
  id: number;
  external_id: string | null;
  sender: string;
  subject: string;
  received_at: string;
  status: string;
  order_id: number | null;
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

export type Change = {
  field: string;
  kind: "quantity" | "price" | "delivery_date" | "size_ratio" | "colour" | "incoterms" | "other";
  old: unknown;
  new: unknown;
  detail: string;
  alert: string | null;
};

export type POSnapshot = Record<ScalarField, string | number | null> & { line_items: LineItem[] };

export type POVersion = {
  id: number;
  version: number;
  email_id: number | null;
  basis: "document" | "thread_reference";
  data: POSnapshot;
  confidence: Record<string, number> | null;
  changes: Change[] | null;
  created_at: string;
};

export type OrderSummary = {
  id: number;
  buyer: string;
  po_number: string;
  style: string | null;
  status: string;
  profile: string;
  current_version: number;
  updated_at: string;
  alerts: string[];
  latest_change_count: number;
};

export type OrderDetail = OrderSummary & { versions: POVersion[] };

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
  orders: () => get<OrderSummary[]>("/orders"),
  agentRun: (id: string) => get<AgentRun>(`/emails/${id}/agent`),
  assess: (id: string, force: boolean) =>
    request<AgentRun>(`/emails/${id}/agent?force=${force}`, { method: "POST" }),
  order: (id: string) => get<OrderDetail>(`/orders/${id}`),
  drafts: (emailId: string) => get<Draft[]>(`/emails/${emailId}/drafts`),
  writeDrafts: (emailId: string, force: boolean) =>
    request<Draft[]>(`/emails/${emailId}/drafts?force=${force}`, { method: "POST" }),
  queue: (status = "pending") => get<Draft[]>(`/drafts?draft_status=${status}`),
  editDraft: (id: number, body: string) =>
    request<Draft>(`/drafts/${id}`, {
      method: "PATCH",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ body }),
    }),
  approveDraft: (id: number, reviewer: string, acknowledgeViolations = false) =>
    request<Draft>(`/drafts/${id}/approve`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ reviewer, acknowledge_violations: acknowledgeViolations }),
    }),
  rejectDraft: (id: number, reviewer: string, reason: string) =>
    request<Draft>(`/drafts/${id}/reject`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ reviewer, reason }),
    }),
  analyse: (id: string, force: boolean) =>
    request<EmailDetail>(`/emails/${id}/analyse?force=${force}`, { method: "POST" }),
};

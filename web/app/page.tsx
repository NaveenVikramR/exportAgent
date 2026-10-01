"use client";

import { useEffect, useState } from "react";
import { api, type Health, type LLMCall, type Route, type TraceSummary } from "@/lib/api";

type Data = {
  health: Health;
  routes: Route[];
  calls: LLMCall[];
  summary: TraceSummary;
};

const TIER_STYLES: Record<string, string> = {
  nano: "bg-emerald-100 text-emerald-800",
  super: "bg-sky-100 text-sky-800",
  ultra: "bg-violet-100 text-violet-800",
};

function TierBadge({ tier }: { tier: string }) {
  return (
    <span
      className={`rounded px-2 py-0.5 text-xs font-medium ${TIER_STYLES[tier] ?? "bg-zinc-100 text-zinc-800"}`}
    >
      {tier}
    </span>
  );
}

function StatusDot({ ok, label }: { ok: boolean; label: string }) {
  return (
    <span className="flex items-center gap-2 text-sm">
      <span className={`h-2 w-2 rounded-full ${ok ? "bg-emerald-500" : "bg-amber-500"}`} />
      {label}
    </span>
  );
}

function Card({ title, children }: { title: string; children: React.ReactNode }) {
  return (
    <section className="rounded-lg border border-zinc-200 bg-white p-5">
      <h2 className="mb-3 text-sm font-semibold uppercase tracking-wide text-zinc-500">{title}</h2>
      {children}
    </section>
  );
}

export default function Home() {
  const [data, setData] = useState<Data | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    Promise.all([api.health(), api.routes(), api.calls(), api.summary()])
      .then(([health, routes, calls, summary]) => setData({ health, routes, calls, summary }))
      .catch((err: Error) => setError(err.message));
  }, []);

  return (
    <main className="mx-auto flex w-full max-w-5xl flex-col gap-6 px-6 py-10">
      <header>
        <h1 className="text-2xl font-semibold">ExportAgent</h1>
        <p className="text-sm text-zinc-600">
          AI export desk for apparel exporters. Milestone 1: system status and agent trace.
        </p>
      </header>

      {error && (
        <div className="rounded-lg border border-red-200 bg-red-50 p-4 text-sm text-red-800">
          Could not reach the backend ({error}). Start it with{" "}
          <code className="font-mono">uvicorn app.main:app --port 8000</code>.
        </div>
      )}

      {!data && !error && <p className="text-sm text-zinc-500">Loading…</p>}

      {data && (
        <>
          <Card title="System status">
            <div className="flex flex-wrap gap-6">
              <StatusDot ok={data.health.status === "ok"} label="API" />
              <StatusDot ok={data.health.database === "ok"} label="Database" />
              <StatusDot
                ok={data.health.nebius_configured}
                label={data.health.nebius_configured ? "Nebius key set" : "Nebius key missing"}
              />
              <StatusDot
                ok={data.health.tavily_configured}
                label={data.health.tavily_configured ? "Tavily key set" : "Tavily key missing"}
              />
            </div>
          </Card>

          <Card title="Model routing">
            <table className="w-full text-left text-sm">
              <thead className="text-zinc-500">
                <tr>
                  <th className="py-1 font-medium">Task</th>
                  <th className="py-1 font-medium">Tier</th>
                  <th className="py-1 font-medium">Model</th>
                </tr>
              </thead>
              <tbody>
                {data.routes.map((route) => (
                  <tr key={route.task_type} className="border-t border-zinc-100">
                    <td className="py-1.5">{route.task_type}</td>
                    <td className="py-1.5">
                      <TierBadge tier={route.tier} />
                    </td>
                    <td className="py-1.5 font-mono text-xs">{route.model}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </Card>

          <Card title="Agent trace">
            <p className="mb-3 text-sm">
              {data.summary.total_calls} calls, running cost{" "}
              <span className="font-mono">${Number(data.summary.total_cost_usd).toFixed(6)}</span>
            </p>
            {data.calls.length === 0 ? (
              <p className="text-sm text-zinc-500">
                No LLM calls yet. Run <code className="font-mono">python -m scripts.smoke_llm</code>.
              </p>
            ) : (
              <div className="overflow-x-auto">
                <table className="w-full text-left text-sm">
                  <thead className="text-zinc-500">
                    <tr>
                      <th className="py-1 font-medium">#</th>
                      <th className="py-1 font-medium">Task</th>
                      <th className="py-1 font-medium">Tier</th>
                      <th className="py-1 font-medium">Model</th>
                      <th className="py-1 text-right font-medium">In</th>
                      <th className="py-1 text-right font-medium">Out</th>
                      <th className="py-1 text-right font-medium">Latency</th>
                      <th className="py-1 text-right font-medium">Cost</th>
                      <th className="py-1 pl-4 font-medium">Result</th>
                    </tr>
                  </thead>
                  <tbody>
                    {data.calls.map((call) => (
                      <tr key={call.id} className="border-t border-zinc-100">
                        <td className="py-1.5 text-zinc-500">{call.id}</td>
                        <td className="py-1.5">{call.task_type}</td>
                        <td className="py-1.5">
                          <TierBadge tier={call.tier} />
                        </td>
                        <td className="py-1.5 font-mono text-xs">{call.model}</td>
                        <td className="py-1.5 text-right">{call.input_tokens}</td>
                        <td className="py-1.5 text-right">{call.output_tokens}</td>
                        <td className="py-1.5 text-right">{call.latency_ms} ms</td>
                        <td className="py-1.5 text-right font-mono text-xs">
                          ${Number(call.cost_usd).toFixed(6)}
                        </td>
                        <td
                          className={`py-1.5 pl-4 ${call.success ? "text-emerald-700" : "text-red-700"}`}
                          title={call.error ?? undefined}
                        >
                          {call.success ? "ok" : "failed"}
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            )}
          </Card>
        </>
      )}
    </main>
  );
}

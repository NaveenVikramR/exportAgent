"use client";

import { useState } from "react";
import type { AgentRun, AgentStep, InfoItem, RiskFlag } from "@/lib/api";

const SEVERITY_STYLES: Record<RiskFlag["severity"], string> = {
  high: "bg-red-600 text-white",
  medium: "bg-amber-400 text-amber-950",
  low: "bg-zinc-200 text-zinc-800",
};

const TOOL_LABELS: Record<string, string> = {
  find_order: "Find order",
  diff_po_versions: "Compare PO versions",
  check_delivery_feasibility: "Check delivery feasibility",
  propose_delivery_options: "Propose delivery options",
  check_compliance: "Check compliance (Tavily)",
  lookup_buyer: "Look up buyer (Tavily)",
  plan: "Ultra plans",
  final: "Ultra writes the report",
  final_retry: "Ultra retries the report",
};

function money(value: string | null | undefined): string {
  return value ? `$${Number(value).toFixed(5)}` : "$0";
}

function Evidence({ item }: { item: string }) {
  if (item.startsWith("http")) {
    return (
      <a href={item} target="_blank" rel="noreferrer" className="break-all text-sky-700 hover:underline">
        {new URL(item).hostname}
      </a>
    );
  }
  return (
    <a href={`#evidence-${item}`} className="rounded bg-zinc-100 px-1.5 font-mono text-zinc-700 hover:bg-zinc-200">
      {item}
    </a>
  );
}

function InfoChecked({ items }: { items: InfoItem[] }) {
  if (items.length === 0) return null;
  return (
    <div>
      <h3 className="mb-1.5 text-sm font-medium text-zinc-700">Info checked (not flags)</h3>
      <ul className="flex flex-col gap-1 text-sm text-zinc-600">
        {items.map((item, index) => (
          <li key={index} className="flex flex-wrap items-baseline gap-2">
            <span className="text-xs uppercase tracking-wide text-zinc-400">{item.topic}</span>
            <span className="min-w-0 flex-1 basis-64">{item.finding}</span>
            <span className="flex flex-wrap gap-1.5 text-xs">
              {item.evidence.map((evidence) => (
                <Evidence key={evidence} item={evidence} />
              ))}
            </span>
          </li>
        ))}
      </ul>
    </div>
  );
}

export function RiskFlags({ run }: { run: AgentRun }) {
  const flags = run.result?.flags ?? [];
  return (
    <div className="flex flex-col gap-3">
      {run.result?.summary && <p className="text-sm">{run.result.summary}</p>}
      {flags.length === 0 && <p className="text-sm text-zinc-500">No risks flagged.</p>}
      <ul className="flex flex-col gap-2">
        {flags.map((flag, index) => (
          <li key={index} className="flex flex-wrap items-start gap-2 rounded border border-zinc-200 p-3 text-sm">
            <span className={`rounded px-2 py-0.5 text-xs font-semibold uppercase ${SEVERITY_STYLES[flag.severity]}`}>
              {flag.severity}
            </span>
            <span className="text-xs uppercase tracking-wide text-zinc-500">{flag.category}</span>
            <span className="min-w-0 flex-1 basis-64">
              {flag.reason}
              {flag.rule && <span className="block text-xs text-zinc-600">Rule: {flag.rule}</span>}
              {flag.adverse_finding && (
                <span className="block text-xs text-zinc-600">Finding: {flag.adverse_finding}</span>
              )}
              {flag.related.length > 0 && (
                <span className="mt-0.5 block text-xs text-zinc-600">
                  Also: {flag.related.join(" · ")}
                </span>
              )}
              {flag.severity_adjusted_from && (
                <span className="block text-xs text-zinc-500">
                  Severity set by the rubric (model said {flag.severity_adjusted_from}).
                </span>
              )}
            </span>
            <span className="flex flex-wrap items-center gap-1.5 text-xs">
              {flag.evidence.map((item) => (
                <Evidence key={item} item={item} />
              ))}
              {!flag.verified && <span className="text-red-700">no verified evidence</span>}
              {flag.source === "rule" && (
                <span className="text-zinc-500" title="Added by a Python safety rule the model's report did not cover">
                  safety rule
                </span>
              )}
            </span>
          </li>
        ))}
      </ul>
      <InfoChecked items={run.result?.info_checked ?? []} />
    </div>
  );
}

function Json({ value }: { value: unknown }) {
  return (
    <pre className="max-h-64 overflow-auto rounded bg-zinc-50 p-2 font-mono text-[11px] leading-snug text-zinc-700">
      {JSON.stringify(value, null, 2)}
    </pre>
  );
}

function StepRow({ step }: { step: AgentStep }) {
  const [open, setOpen] = useState(false);
  const isLlm = step.kind === "llm";
  const reasoning = isLlm ? (step.output?.reasoning as string | undefined) : undefined;
  return (
    <li id={step.evidence_id ? `evidence-${step.evidence_id}` : undefined} className="scroll-mt-20">
      <button
        onClick={() => setOpen(!open)}
        className="flex w-full flex-wrap items-baseline gap-x-3 gap-y-1 rounded px-2 py-1.5 text-left text-sm hover:bg-zinc-50"
      >
        <span className="w-14 shrink-0 text-xs text-zinc-400">
          {step.round === 0 ? "pre-fetch" : `round ${step.round}`}
        </span>
        <span
          className={`rounded px-1.5 py-0.5 text-xs font-medium ${
            isLlm ? "bg-violet-100 text-violet-800" : step.round === 0 ? "bg-zinc-100 text-zinc-700" : "bg-sky-100 text-sky-800"
          }`}
        >
          {isLlm ? "Ultra" : step.round === 0 ? "Python" : "tool"}
        </span>
        <span className="font-medium">{TOOL_LABELS[step.name] ?? step.name}</span>
        {step.evidence_id && <span className="font-mono text-xs text-zinc-500">{step.evidence_id}</span>}
        <span className="min-w-0 flex-1 basis-60 text-zinc-600">{step.summary}</span>
        {isLlm && (
          <span className="text-xs tabular-nums text-zinc-500">
            {step.input_tokens?.toLocaleString()} in / {step.output_tokens?.toLocaleString()} out ·{" "}
            {step.latency_ms?.toLocaleString()} ms · {money(step.cost_usd)}
            {step.call_source && step.call_source !== "live" ? ` · ${step.call_source}` : ""}
          </span>
        )}
      </button>
      {open && (
        <div className="mb-2 ml-16 flex flex-col gap-2 text-xs">
          {isLlm && step.model && <p className="font-mono text-zinc-500">{step.model}</p>}
          {reasoning && (
            <div>
              <p className="mb-1 font-medium text-zinc-600">Reasoning (excerpt)</p>
              <p className="whitespace-pre-wrap text-zinc-700">{reasoning}</p>
            </div>
          )}
          {!isLlm && (
            <>
              <p className="font-medium text-zinc-600">Input</p>
              <Json value={step.input} />
              <p className="font-medium text-zinc-600">Result</p>
              <Json value={step.output} />
            </>
          )}
          {isLlm && step.output && (step.output.tool_calls as unknown[])?.length > 0 && (
            <Json value={step.output.tool_calls} />
          )}
        </div>
      )}
    </li>
  );
}

export function AgentTrace({ run }: { run: AgentRun }) {
  return (
    <div className="flex flex-col gap-2">
      <p className="text-xs text-zinc-500">
        Pre-fetched checks run in Python first; then {run.rounds} tool {run.rounds === 1 ? "round" : "rounds"} (cap
        8) · {run.ultra_calls} Ultra {run.ultra_calls === 1 ? "call" : "calls"} · {money(run.total_cost_usd)} total.
        Click a step for its inputs and result.
      </p>
      <ol className="flex flex-col">
        {run.steps.map((step) => (
          <StepRow key={step.id} step={step} />
        ))}
      </ol>
    </div>
  );
}

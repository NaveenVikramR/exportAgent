"use client";

import Link from "next/link";
import { useParams } from "next/navigation";
import { useEffect, useState } from "react";
import { CATEGORY_LABELS, CategoryBadge, StatusBadge } from "@/components/badges";
import { api, type EmailDetail, type Extraction, type ScalarField } from "@/lib/api";

const FIELD_LABELS: [ScalarField, string][] = [
  ["buyer", "Buyer"],
  ["po_number", "PO number"],
  ["style", "Style"],
  ["currency", "Currency"],
  ["unit_price", "Unit price"],
  ["total_quantity", "Total quantity"],
  ["delivery_date", "Delivery date"],
  ["incoterms", "Incoterms"],
  ["port", "Port"],
  ["destination_country", "Destination"],
];

const REASON_LABELS: Record<string, string> = {
  missing: "Missing",
  low_confidence: "Low confidence",
  evidence_not_found: "Source quote not found",
  quantity_mismatch: "Quantities do not add up",
};

function Card({ title, children }: { title: string; children: React.ReactNode }) {
  return (
    <section className="rounded-lg border border-zinc-200 bg-white p-5">
      <h2 className="mb-3 text-sm font-semibold uppercase tracking-wide text-zinc-500">{title}</h2>
      {children}
    </section>
  );
}

function Confidence({ value }: { value: number }) {
  const colour = value >= 0.7 ? "bg-emerald-500" : value >= 0.4 ? "bg-amber-500" : "bg-red-500";
  return (
    <span className="flex items-center gap-2">
      <span className="h-1.5 w-16 rounded bg-zinc-100">
        <span className={`block h-1.5 rounded ${colour}`} style={{ width: `${Math.round(value * 100)}%` }} />
      </span>
      <span className="w-9 text-right text-xs tabular-nums text-zinc-600">{Math.round(value * 100)}%</span>
    </span>
  );
}

function ExtractionTable({ extraction }: { extraction: Extraction }) {
  const flags = new Map(extraction.review.map((flag) => [flag.field, flag]));
  const lineFlags = extraction.review.filter((flag) => flag.field === "line_items");
  const items = extraction.fields.line_items;
  const sizes = Array.from(new Set(items.flatMap((item) => Object.keys(item.sizes))));

  return (
    <>
      <table className="w-full text-left text-sm">
        <thead className="text-zinc-500">
          <tr>
            <th className="py-1 font-medium">Field</th>
            <th className="py-1 font-medium">Value</th>
            <th className="py-1 font-medium">Confidence</th>
            <th className="py-1 font-medium">Source text</th>
          </tr>
        </thead>
        <tbody>
          {FIELD_LABELS.map(([name, label]) => {
            const field = extraction.fields[name];
            const flag = flags.get(name);
            return (
              <tr key={name} className={`border-t border-zinc-100 align-top ${flag ? "bg-amber-50" : ""}`}>
                <td className="py-2 pr-3 text-zinc-600">{label}</td>
                <td className="py-2 pr-3 font-medium">
                  {field.value ?? <span className="font-normal text-zinc-400">not stated</span>}
                  {flag && (
                    <p className="mt-0.5 text-xs font-normal text-amber-900">
                      {REASON_LABELS[flag.reason] ?? flag.reason}. {flag.detail}
                    </p>
                  )}
                </td>
                <td className="py-2 pr-3">
                  <Confidence value={field.confidence} />
                </td>
                <td className="py-2 text-xs text-zinc-500">{field.evidence}</td>
              </tr>
            );
          })}
        </tbody>
      </table>

      {items.length > 0 && (
        <div className="mt-5 overflow-x-auto">
          <h3 className="mb-2 text-sm font-medium">Line items</h3>
          <table className="w-full text-left text-sm">
            <thead className="text-zinc-500">
              <tr>
                <th className="py-1 font-medium">Colour</th>
                {sizes.map((size) => (
                  <th key={size} className="py-1 text-right font-medium">
                    {size}
                  </th>
                ))}
                <th className="py-1 text-right font-medium">Quantity</th>
              </tr>
            </thead>
            <tbody>
              {items.map((item, index) => (
                <tr key={index} className="border-t border-zinc-100">
                  <td className="py-1.5">{item.colour}</td>
                  {sizes.map((size) => (
                    <td key={size} className="py-1.5 text-right tabular-nums">
                      {item.sizes[size] ?? ""}
                    </td>
                  ))}
                  <td className="py-1.5 text-right font-medium tabular-nums">{item.quantity}</td>
                </tr>
              ))}
            </tbody>
          </table>
          {lineFlags.map((flag, index) => (
            <p key={index} className="mt-2 rounded bg-amber-50 px-3 py-2 text-xs text-amber-900">
              {flag.detail}
            </p>
          ))}
        </div>
      )}
    </>
  );
}

export default function EmailPage() {
  const { id } = useParams<{ id: string }>();
  const [email, setEmail] = useState<EmailDetail | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [running, setRunning] = useState(false);

  useEffect(() => {
    api
      .email(id)
      .then(setEmail)
      .catch((err: Error) => setError(err.message));
  }, [id]);

  async function analyse(force: boolean) {
    setRunning(true);
    setError(null);
    try {
      setEmail(await api.analyse(id, force));
    } catch (err) {
      setError((err as Error).message);
    } finally {
      setRunning(false);
    }
  }

  return (
    <main className="mx-auto flex w-full max-w-5xl flex-col gap-6 px-6 py-10">
      <Link href="/" className="text-sm text-zinc-600 hover:text-zinc-900">
        ← Inbox
      </Link>

      {error && (
        <div className="rounded-lg border border-red-200 bg-red-50 p-4 text-sm text-red-800">{error}</div>
      )}
      {!email && !error && <p className="text-sm text-zinc-500">Loading…</p>}

      {email && (
        <>
          <header className="flex items-start justify-between gap-4">
            <div className="min-w-0">
              <h1 className="text-xl font-semibold">{email.subject}</h1>
              <p className="text-sm text-zinc-600">{email.sender}</p>
            </div>
            <div className="flex shrink-0 items-center gap-2">
              <StatusBadge status={email.status} />
              <button
                onClick={() => analyse(email.classification !== null)}
                disabled={running}
                className="rounded bg-zinc-900 px-3 py-1.5 text-sm font-medium text-white hover:bg-zinc-700 disabled:opacity-50"
              >
                {running ? "Analysing…" : email.classification ? "Re-run analysis" : "Analyse"}
              </button>
            </div>
          </header>

          {email.notice && (
            <p className="rounded border border-sky-200 bg-sky-50 px-3 py-2 text-sm text-sky-900">{email.notice}</p>
          )}
          {email.analysis_error && (
            <p className="rounded border border-red-200 bg-red-50 px-3 py-2 text-sm text-red-800">
              The last analysis did not complete and needs a manual check: {email.analysis_error}
            </p>
          )}

          {email.classification && (
            <Card title="Classification">
              <div className="flex flex-wrap items-center gap-2">
                <CategoryBadge category={email.classification.category} />
                {email.classification.intents
                  .filter((intent) => intent !== email.classification?.category)
                  .map((intent) => (
                    <span key={intent} className="text-xs text-zinc-600">
                      + {CATEGORY_LABELS[intent] ?? intent}
                    </span>
                  ))}
                <span className="ml-auto">
                  <Confidence value={email.classification.confidence} />
                </span>
              </div>
              <p className="mt-2 text-sm">{email.classification.summary}</p>
            </Card>
          )}

          {email.extraction && (
            <Card
              title={
                email.extraction.review.length > 0
                  ? `Extracted order data (${email.extraction.review.length} to review)`
                  : "Extracted order data"
              }
            >
              <ExtractionTable extraction={email.extraction} />
            </Card>
          )}
          {email.classification && !email.extraction && (
            <p className="text-sm text-zinc-500">This email carries no purchase order data, so nothing was extracted.</p>
          )}

          <Card title="Email">
            <pre className="whitespace-pre-wrap font-sans text-sm">{email.body}</pre>
          </Card>
          {email.attachments.map((attachment) => (
            <Card key={attachment.id} title={`Attachment: ${attachment.filename}`}>
              <pre className="overflow-x-auto font-mono text-xs">{attachment.text_content}</pre>
            </Card>
          ))}
        </>
      )}
    </main>
  );
}

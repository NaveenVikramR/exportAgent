"use client";

import { useState } from "react";
import { API_URL, api, type ExportDocument } from "@/lib/api";

const KIND_LABELS: Record<ExportDocument["kind"], string> = {
  commercial_invoice: "Commercial Invoice",
  packing_list: "Packing List",
};

function headline(doc: ExportDocument): string {
  const t = doc.totals;
  if (doc.kind === "commercial_invoice") {
    const amount = t.total_amount ? `${t.currency} ${Number(t.total_amount).toLocaleString("en-US", { minimumFractionDigits: 2 })}` : "amount to be confirmed";
    return `${Number(t.total_quantity).toLocaleString("en-US")} pcs · ${amount}`;
  }
  const gross = t.total_gross_kg ? `${Number(t.total_gross_kg).toLocaleString("en-US")} kg gross` : "weights to be confirmed";
  return `${t.total_cartons} cartons · ${Number(t.total_quantity).toLocaleString("en-US")} pcs · ${gross}`;
}

export function DocumentList({ documents }: { documents: ExportDocument[] }) {
  return (
    <ul className="flex flex-col gap-2">
      {documents.map((doc) => (
        <li key={doc.id} className="rounded border border-zinc-200 px-3 py-2 text-sm">
          <div className="flex flex-wrap items-baseline gap-x-3 gap-y-1">
            <a
              href={`${API_URL}${doc.download_url}`}
              target="_blank"
              rel="noreferrer"
              className="font-medium text-sky-700 hover:underline"
            >
              {KIND_LABELS[doc.kind]} (PDF)
            </a>
            <span className="font-mono text-xs text-zinc-500">{doc.number}</span>
            <span className="text-xs text-zinc-500">PO version {doc.po_version}</span>
            {doc.shipment && <span className="text-xs font-medium text-zinc-700">{doc.shipment}</span>}
            <span className="ml-auto text-xs text-zinc-600">{headline(doc)}</span>
          </div>
          {doc.tbc_fields.length > 0 && (
            <p className="mt-1 text-xs text-red-800">
              To be confirmed before use: {doc.tbc_fields.join(", ")}
            </p>
          )}
        </li>
      ))}
    </ul>
  );
}

/** Generate button plus the latest documents; used on the order page and after a reply is approved. */
export function GenerateDocuments({
  orderId,
  enabled,
  disabledReason,
  initial = [],
}: {
  orderId: number;
  enabled: boolean;
  disabledReason?: string;
  initial?: ExportDocument[];
}) {
  const [documents, setDocuments] = useState<ExportDocument[]>(initial);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function generate() {
    setBusy(true);
    setError(null);
    try {
      const created = await api.generateDocuments(orderId);
      setDocuments((current) => [...created, ...current]);
    } catch (err) {
      setError((err as Error).message);
    } finally {
      setBusy(false);
    }
  }

  // The newest pair first; older generations stay listed below.
  return (
    <div className="flex flex-col gap-3">
      <div className="flex flex-wrap items-center gap-3">
        <button
          onClick={generate}
          disabled={busy || !enabled}
          title={enabled ? undefined : disabledReason}
          className="rounded bg-zinc-900 px-3 py-1.5 text-sm font-medium text-white hover:bg-zinc-700 disabled:opacity-50"
        >
          {busy ? "Generating…" : documents.length ? "Generate again" : "Generate documents"}
        </button>
        {!enabled && disabledReason && <span className="text-sm text-zinc-500">{disabledReason}</span>}
      </div>
      {error && <p className="text-sm text-red-700">{error}</p>}
      {documents.length > 0 && <DocumentList documents={documents} />}
    </div>
  );
}

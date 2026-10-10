"use client";

import { useEffect, useState } from "react";
import { ReviewerField, useReviewer } from "@/components/draft-card";
import { api, type DecisionOption } from "@/lib/api";

export const ORDER_STATUS_LABELS: Record<string, string> = {
  open: "Open",
  awaiting_buyer: "Awaiting buyer",
  confirmed: "Confirmed",
};

const STATUS_STYLES: Record<string, string> = {
  open: "bg-zinc-100 text-zinc-700",
  awaiting_buyer: "bg-amber-100 text-amber-900",
  confirmed: "bg-emerald-100 text-emerald-800",
};

export function OrderStatusBadge({ status }: { status: string }) {
  return (
    <span className={`whitespace-nowrap rounded px-2 py-0.5 text-xs font-medium ${STATUS_STYLES[status] ?? STATUS_STYLES.open}`}>
      {ORDER_STATUS_LABELS[status] ?? status}
    </span>
  );
}

/** Pick which plan the buyer accepted; creates an internal PO version and confirms the order. */
export function BuyerDecision({ orderId, onRecorded }: { orderId: number; onRecorded: () => void }) {
  const [options, setOptions] = useState<DecisionOption[] | null>(null);
  const [choice, setChoice] = useState<string>("");
  const [reviewer, setReviewer] = useReviewer();
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    api
      .decisionOptions(orderId)
      .then(setOptions)
      .catch((err: Error) => setError(err.message));
  }, [orderId]);

  async function record() {
    setBusy(true);
    setError(null);
    try {
      await api.recordDecision(orderId, choice, reviewer);
      onRecorded();
    } catch (err) {
      setError((err as Error).message);
    } finally {
      setBusy(false);
    }
  }

  if (!options) return error ? <p className="text-sm text-red-700">{error}</p> : null;
  return (
    <div className="flex flex-col gap-3">
      <fieldset className="flex flex-col gap-2">
        {options.map((option) => (
          <label key={option.id} className="flex items-start gap-2 text-sm">
            <input
              type="radio"
              name={`decision-${orderId}`}
              value={option.id}
              checked={choice === option.id}
              onChange={() => setChoice(option.id)}
              className="mt-0.5"
            />
            {option.label}
          </label>
        ))}
      </fieldset>
      <div className="flex flex-wrap items-center gap-3">
        <ReviewerField name={reviewer} onChange={setReviewer} />
        <button
          onClick={record}
          disabled={busy || !choice || !reviewer}
          className="rounded bg-zinc-900 px-3 py-1.5 text-sm font-medium text-white hover:bg-zinc-700 disabled:opacity-50"
        >
          {busy ? "Recording…" : "Record buyer decision"}
        </button>
      </div>
      {error && <p className="text-sm text-red-700">{error}</p>}
    </div>
  );
}

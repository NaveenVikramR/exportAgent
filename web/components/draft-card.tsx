"use client";

import Link from "next/link";
import { useState, useSyncExternalStore } from "react";
import { api, type Draft } from "@/lib/api";

const REVIEWER_KEY = "exportagent.reviewer";
const REVIEWER_EVENT = "exportagent-reviewer";
// Fallback when browser storage is unavailable: the name lasts for this page view.
let reviewerInMemory = "";

function subscribeReviewer(callback: () => void) {
  window.addEventListener("storage", callback);
  window.addEventListener(REVIEWER_EVENT, callback);
  return () => {
    window.removeEventListener("storage", callback);
    window.removeEventListener(REVIEWER_EVENT, callback);
  };
}

function readReviewer(): string {
  try {
    return localStorage.getItem(REVIEWER_KEY) ?? reviewerInMemory;
  } catch {
    return reviewerInMemory;
  }
}

/** The reviewer's name, remembered in this browser. There is no login in the demo. */
export function useReviewer(): [string, (name: string) => void] {
  const name = useSyncExternalStore(subscribeReviewer, readReviewer, () => "");
  function update(next: string) {
    reviewerInMemory = next;
    try {
      localStorage.setItem(REVIEWER_KEY, next);
    } catch {
      // storage unavailable: keep the in-memory value
    }
    window.dispatchEvent(new Event(REVIEWER_EVENT));
  }
  return [name, update];
}

export function ReviewerField({ name, onChange }: { name: string; onChange: (name: string) => void }) {
  return (
    <label className="flex items-center gap-2 text-sm text-zinc-600">
      Reviewing as
      <input
        value={name}
        onChange={(event) => onChange(event.target.value)}
        placeholder="your name"
        className="w-40 rounded border border-zinc-300 px-2 py-1 text-sm text-zinc-900"
      />
    </label>
  );
}

const KIND_LABELS: Record<Draft["kind"], string> = {
  buyer_reply: "Reply to buyer",
  internal_note: "Internal note for production",
};

function when(value: string | null): string {
  return value ? new Date(value).toLocaleString("en-GB", { dateStyle: "medium", timeStyle: "short" }) : "";
}

export function DraftCard({
  draft,
  reviewer,
  onChange,
  showEmail = false,
}: {
  draft: Draft;
  reviewer: string;
  onChange: (draft: Draft) => void;
  showEmail?: boolean;
}) {
  const [editing, setEditing] = useState(false);
  const [text, setText] = useState(draft.text);
  const [acknowledged, setAcknowledged] = useState(false);
  const [rejecting, setRejecting] = useState(false);
  const [reason, setReason] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const pending = draft.status === "pending";
  const hasViolations = draft.violations.length > 0;

  async function act(action: () => Promise<Draft>) {
    setBusy(true);
    setError(null);
    try {
      const updated = await action();
      onChange(updated);
      setText(updated.text);
      setEditing(false);
      setRejecting(false);
    } catch (err) {
      setError((err as Error).message);
    } finally {
      setBusy(false);
    }
  }

  return (
    <article className="rounded-lg border border-zinc-200 bg-white p-4">
      <header className="mb-2 flex flex-wrap items-baseline gap-x-3 gap-y-1">
        <h3 className="font-medium">{KIND_LABELS[draft.kind]}</h3>
        {showEmail && (
          <Link href={`/emails/${draft.email_id}`} className="text-sm text-sky-700 hover:underline">
            {draft.email_subject}
          </Link>
        )}
        <span className="ml-auto text-xs text-zinc-500">
          {draft.model ?? "model"} · ${Number(draft.cost_usd ?? 0).toFixed(5)}
        </span>
      </header>
      {draft.kind === "buyer_reply" && draft.subject && (
        <p className="mb-1 text-sm text-zinc-600">Subject: {draft.subject}</p>
      )}

      {hasViolations ? (
        <div className="mb-2 rounded border border-red-200 bg-red-50 px-3 py-2 text-sm text-red-900">
          <p className="font-medium">Fact check: {draft.violations.length} value(s) not found in the order data or the email</p>
          <ul className="mt-1 list-inside list-disc">
            {draft.violations.map((violation, index) => (
              <li key={index}>
                <span className="font-mono">{violation.text}</span> ({violation.kind})
              </li>
            ))}
          </ul>
        </div>
      ) : (
        <p className="mb-2 text-xs text-emerald-700">
          Fact check passed: {draft.checked} {draft.checked === 1 ? "value" : "values"} checked against the sources.
        </p>
      )}

      {editing ? (
        <textarea
          value={text}
          onChange={(event) => setText(event.target.value)}
          rows={Math.min(24, Math.max(8, text.split("\n").length + 2))}
          className="w-full rounded border border-zinc-300 p-2 font-sans text-sm"
        />
      ) : (
        <pre className="whitespace-pre-wrap rounded bg-zinc-50 p-3 font-sans text-sm">{draft.text}</pre>
      )}
      {draft.edited_body !== null && !editing && <p className="mt-1 text-xs text-zinc-500">Edited by the reviewer.</p>}

      {error && <p className="mt-2 text-sm text-red-700">{error}</p>}

      {pending && (
        <div className="mt-3 flex flex-wrap items-center gap-2">
          {editing ? (
            <>
              <button
                disabled={busy}
                onClick={() => act(() => api.editDraft(draft.id, text))}
                className="rounded bg-zinc-900 px-3 py-1.5 text-sm font-medium text-white disabled:opacity-50"
              >
                Save edit
              </button>
              <button onClick={() => setEditing(false)} className="px-2 text-sm text-zinc-600">
                Cancel
              </button>
            </>
          ) : rejecting ? (
            <>
              <input
                value={reason}
                onChange={(event) => setReason(event.target.value)}
                placeholder="Reason (optional)"
                className="min-w-0 flex-1 rounded border border-zinc-300 px-2 py-1 text-sm"
              />
              <button
                disabled={busy || !reviewer}
                onClick={() => act(() => api.rejectDraft(draft.id, reviewer, reason))}
                className="rounded bg-red-700 px-3 py-1.5 text-sm font-medium text-white disabled:opacity-50"
              >
                Confirm reject
              </button>
              <button onClick={() => setRejecting(false)} className="px-2 text-sm text-zinc-600">
                Cancel
              </button>
            </>
          ) : (
            <>
              <button
                disabled={busy || !reviewer || (hasViolations && !acknowledged)}
                onClick={() => act(() => api.approveDraft(draft.id, reviewer, acknowledged))}
                className="rounded bg-emerald-700 px-3 py-1.5 text-sm font-medium text-white disabled:opacity-50"
                title={reviewer ? undefined : "Enter your name first"}
              >
                Approve and mark sent
              </button>
              <button onClick={() => setEditing(true)} className="rounded border border-zinc-300 px-3 py-1.5 text-sm">
                Edit
              </button>
              <button onClick={() => setRejecting(true)} className="rounded border border-zinc-300 px-3 py-1.5 text-sm">
                Reject
              </button>
              {hasViolations && (
                <label className="flex items-center gap-1.5 text-xs text-red-900">
                  <input type="checkbox" checked={acknowledged} onChange={(e) => setAcknowledged(e.target.checked)} />
                  I have checked the flagged values
                </label>
              )}
              {!reviewer && <span className="text-xs text-zinc-500">Enter your name to approve or reject.</span>}
            </>
          )}
        </div>
      )}

      {draft.status === "sent" && (
        <p className="mt-3 text-sm text-emerald-800">
          Approved and marked sent by {draft.reviewed_by} on {when(draft.sent_at)}. (Demo: no email leaves the system.)
        </p>
      )}
      {draft.status === "rejected" && (
        <p className="mt-3 text-sm text-red-800">
          Rejected by {draft.reviewed_by} on {when(draft.reviewed_at)}
          {draft.reject_reason ? `: ${draft.reject_reason}` : "."}
        </p>
      )}
    </article>
  );
}

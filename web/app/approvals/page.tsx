"use client";

import { useEffect, useState } from "react";
import { DraftCard, ReviewerField, useReviewer } from "@/components/draft-card";
import { api, type Draft } from "@/lib/api";

const TABS = [
  { status: "pending", label: "Waiting for approval" },
  { status: "sent", label: "Approved (marked sent)" },
  { status: "rejected", label: "Rejected" },
];

export default function Approvals() {
  const [tab, setTab] = useState("pending");
  const [drafts, setDrafts] = useState<Draft[] | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [reviewer, setReviewer] = useReviewer();

  useEffect(() => {
    api
      .queue(tab)
      .then((rows) => {
        setDrafts(rows);
        setError(null);
      })
      .catch((err: Error) => setError(err.message));
  }, [tab]);

  function replace(updated: Draft) {
    // A draft that leaves the current tab drops out of the list.
    setDrafts((rows) => (rows ?? []).flatMap((row) => (row.id !== updated.id ? [row] : updated.status === tab ? [updated] : [])));
  }

  return (
    <main className="mx-auto flex w-full max-w-5xl flex-col gap-6 px-6 py-10">
      <header className="flex flex-wrap items-end justify-between gap-3">
        <div>
          <h1 className="text-2xl font-semibold">Approvals</h1>
          <p className="text-sm text-zinc-600">
            Nothing is sent automatically. Every draft waits here for a person to edit, approve or reject it.
          </p>
        </div>
        <ReviewerField name={reviewer} onChange={setReviewer} />
      </header>

      <nav className="flex gap-1 border-b border-zinc-200">
        {TABS.map((item) => (
          <button
            key={item.status}
            onClick={() => {
              setDrafts(null);
              setTab(item.status);
            }}
            className={`-mb-px border-b-2 px-3 py-2 text-sm ${
              tab === item.status ? "border-zinc-900 font-medium" : "border-transparent text-zinc-500 hover:text-zinc-800"
            }`}
          >
            {item.label}
          </button>
        ))}
      </nav>

      {error && <div className="rounded-lg border border-red-200 bg-red-50 p-4 text-sm text-red-800">{error}</div>}
      {!drafts && !error && <p className="text-sm text-zinc-500">Loading…</p>}
      {drafts?.length === 0 && <p className="text-sm text-zinc-500">Nothing here.</p>}
      <div className="flex flex-col gap-4">
        {drafts?.map((draft) => (
          <DraftCard key={draft.id} draft={draft} reviewer={reviewer} onChange={replace} showEmail />
        ))}
      </div>
    </main>
  );
}

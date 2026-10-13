"use client";

import { useEffect, useState } from "react";
import { DraftCard, ReviewerField, useReviewer } from "@/components/draft-card";
import { MatchQuestions } from "@/components/match-questions";
import { Empty, ErrorBox, Loading, Page } from "@/components/ui";
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
    <Page>
      <header className="flex flex-wrap items-end justify-between gap-3">
        <div>
          <h1 className="text-2xl font-semibold">Approvals</h1>
          <p className="text-sm text-zinc-600">
            Nothing is sent automatically. Every draft waits here for a person to edit, approve or reject it.
          </p>
        </div>
        <ReviewerField name={reviewer} onChange={setReviewer} />
      </header>

      <MatchQuestions reviewer={reviewer} />

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

      {error && <ErrorBox>{error}</ErrorBox>}
      {!drafts && !error && <Loading />}
      {drafts?.length === 0 && (
        <Empty title={tab === "pending" ? "Nothing waiting for approval" : "Nothing here yet"}>
          {tab === "pending" ? "Drafts appear here when an email has been analysed and a reply drafted." : null}
        </Empty>
      )}
      <div className="flex flex-col gap-4">
        {drafts?.map((draft) => (
          <DraftCard key={draft.id} draft={draft} reviewer={reviewer} onChange={replace} showEmail />
        ))}
      </div>
    </Page>
  );
}

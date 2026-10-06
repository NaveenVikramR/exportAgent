"use client";

import Link from "next/link";
import { useEffect, useState } from "react";
import { CategoryBadge, StatusBadge } from "@/components/badges";
import { api, type EmailSummary } from "@/lib/api";

export default function Inbox() {
  const [emails, setEmails] = useState<EmailSummary[] | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    api
      .emails()
      .then(setEmails)
      .catch((err: Error) => setError(err.message));
  }, []);

  return (
    <main className="mx-auto flex w-full max-w-5xl flex-col gap-6 px-6 py-10">
      <header>
        <h1 className="text-2xl font-semibold">Inbox</h1>
        <p className="text-sm text-zinc-600">Buyer emails, classified and checked before anyone replies.</p>
      </header>

      {error && (
        <div className="rounded-lg border border-red-200 bg-red-50 p-4 text-sm text-red-800">
          Could not load the inbox: {error}
        </div>
      )}
      {!emails && !error && <p className="text-sm text-zinc-500">Loading…</p>}
      {emails?.length === 0 && (
        <p className="text-sm text-zinc-500">
          No emails yet. Load the demo inbox with <code className="font-mono">python -m scripts.seed</code>.
        </p>
      )}

      {emails && emails.length > 0 && (
        <ul className="divide-y divide-zinc-100 rounded-lg border border-zinc-200 bg-white">
          {emails.map((email) => (
            <li key={email.id}>
              <Link href={`/emails/${email.id}`} className="flex items-start gap-4 px-5 py-4 hover:bg-zinc-50">
                <div className="min-w-0 flex-1">
                  <p className="truncate text-sm font-medium">{email.subject}</p>
                  <p className="truncate text-sm text-zinc-500">{email.sender}</p>
                  {email.classification && (
                    <p className="mt-1 truncate text-sm text-zinc-600">{email.classification.summary}</p>
                  )}
                </div>
                <div className="flex shrink-0 flex-col items-end gap-1.5">
                  <span className="text-xs text-zinc-500">
                    {new Date(email.received_at).toLocaleDateString("en-GB", {
                      day: "numeric",
                      month: "short",
                      year: "numeric",
                    })}
                  </span>
                  <div className="flex gap-1.5">
                    {email.classification && <CategoryBadge category={email.classification.category} />}
                    <StatusBadge status={email.status} />
                  </div>
                  {email.review_count > 0 && (
                    <span className="text-xs text-amber-800">
                      {email.review_count} {email.review_count === 1 ? "field" : "fields"} to review
                    </span>
                  )}
                </div>
              </Link>
            </li>
          ))}
        </ul>
      )}
    </main>
  );
}

"use client";

import Link from "next/link";
import { useEffect, useState } from "react";
import { api, type MatchQuestion } from "@/lib/api";

// Emails the matcher was unsure about: a person says whether they belong to an existing order,
// so an uncertain match never creates a duplicate order on its own.
export function MatchQuestions({ reviewer }: { reviewer: string }) {
  const [questions, setQuestions] = useState<MatchQuestion[]>([]);
  const [busy, setBusy] = useState<number | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    api
      .matchQuestions()
      .then(setQuestions)
      .catch((err: Error) => setError(err.message));
  }, []);

  async function answer(question: MatchQuestion, sameOrder: boolean) {
    setBusy(question.email_id);
    try {
      await api.answerMatch(question.email_id, sameOrder, reviewer);
      setQuestions((rows) => rows.filter((row) => row.email_id !== question.email_id));
      setError(null);
    } catch (err) {
      setError((err as Error).message);
    } finally {
      setBusy(null);
    }
  }

  if (questions.length === 0 && !error) return null;

  return (
    <section className="flex flex-col gap-3 rounded-lg border border-amber-200 bg-amber-50 p-4">
      <h2 className="text-sm font-semibold text-amber-900">Is this the same order?</h2>
      {error && <p className="text-sm text-red-700">{error}</p>}
      {questions.map((question) => (
        <div key={question.email_id} className="flex flex-col gap-2 rounded-md border border-amber-100 bg-white p-3 text-sm">
          <div>
            <Link href={`/emails/${question.email_id}`} className="font-medium hover:underline">
              {question.subject}
            </Link>
            <span className="text-zinc-500"> · {question.sender}</span>
          </div>
          <p>
            {question.question}{" "}
            <Link href={`/orders/${question.candidate_order_id}`} className="text-zinc-500 underline">
              view order
            </Link>
          </p>
          <p className="text-xs text-zinc-500">
            Match score {question.score.toFixed(2)}: {question.reasons.join("; ")}
          </p>
          <div className="flex gap-2">
            <button
              disabled={!reviewer || busy === question.email_id}
              onClick={() => answer(question, true)}
              className="rounded-md bg-zinc-900 px-3 py-1.5 text-white disabled:opacity-40"
            >
              Yes, same order
            </button>
            <button
              disabled={!reviewer || busy === question.email_id}
              onClick={() => answer(question, false)}
              className="rounded-md border border-zinc-300 px-3 py-1.5 disabled:opacity-40"
            >
              No, a new order
            </button>
            {!reviewer && <span className="self-center text-xs text-zinc-500">Enter your name to answer.</span>}
          </div>
        </div>
      ))}
    </section>
  );
}

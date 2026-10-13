"use client";

import Link from "next/link";
import { useCallback, useEffect, useState } from "react";
import { EmailList } from "@/components/email-list";
import { Button, Card, Empty, ErrorBox, Loading, Notice, Page, Stat, money } from "@/components/ui";
import { api, type Dashboard } from "@/lib/api";

const CATEGORY_LABELS: Record<string, string> = {
  delivery: "Delivery",
  capacity: "Capacity",
  price: "Contract value",
  quantity: "Quantity",
};

export default function DashboardPage() {
  const [data, setData] = useState<Dashboard | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [resetting, setResetting] = useState(false);
  const [notice, setNotice] = useState<string | null>(null);

  const load = useCallback(() => {
    api
      .dashboard()
      .then(setData)
      .catch((err: Error) => setError(err.message));
  }, []);
  useEffect(load, [load]);
  const retry = () => {
    setError(null);
    load();
  };

  async function reset() {
    setResetting(true);
    try {
      const result = await api.resetDemo();
      setNotice(`Demo restored: ${result.emails} emails, as first analysed.`);
      load();
    } catch (err) {
      setError((err as Error).message);
    } finally {
      setResetting(false);
    }
  }

  const approvals = data ? data.drafts_pending + data.match_questions : 0;
  const spent = data ? Number(data.spend.today_usd) : 0;
  const cap = data ? Number(data.spend.cap_usd) : 1;

  return (
    <Page wide>
      <section className="flex flex-col gap-3 rounded-2xl border border-zinc-200 bg-white p-6 shadow-sm md:flex-row md:items-center md:justify-between">
        <div className="max-w-2xl">
          <h1 className="text-2xl font-semibold tracking-tight">Your AI export desk</h1>
          <p className="mt-1 text-sm text-zinc-600">
            ExportAgent reads every buyer email and PO, finds what changed, checks whether the factory can still make it,
            and drafts the reply and the export documents. A person approves everything before it goes out.
          </p>
        </div>
        <div className="flex shrink-0 flex-wrap gap-2">
          {data?.demo_email_id && (
            <Link
              href={`/emails/${data.demo_email_id}`}
              className="rounded-md bg-emerald-600 px-4 py-2 text-sm font-medium text-white hover:bg-emerald-700"
            >
              Start the demo story →
            </Link>
          )}
          <Link href="/try" className="rounded-md border border-zinc-300 bg-white px-4 py-2 text-sm font-medium hover:bg-zinc-50">
            Try your own email
          </Link>
        </div>
      </section>

      {notice && <Notice tone="ok">{notice}</Notice>}
      {error && <ErrorBox retry={retry}>Could not load the dashboard: {error}</ErrorBox>}
      {!data && !error && <Loading />}

      {data && (
        <>
          <div className="grid grid-cols-2 gap-3 lg:grid-cols-4">
            <Stat label="Open orders" value={data.open_orders} hint={`${data.awaiting_buyer} awaiting the buyer`} href="/orders" />
            <Stat
              label="Needs approval"
              value={approvals}
              hint={`${data.drafts_pending} drafts · ${data.match_questions} order questions`}
              href="/approvals"
            />
            <Stat
              label="High risks"
              value={data.high_risks.length}
              hint="infeasible plans, large value changes"
              tone={data.high_risks.length ? "alert" : "default"}
            />
            <Stat
              label="AI cost today"
              value={money(data.spend.today_usd, 3)}
              hint={
                <span className="flex items-center gap-2">
                  <span className="h-1.5 flex-1 rounded bg-zinc-100">
                    <span
                      className={`block h-1.5 rounded ${spent / cap > 0.8 ? "bg-red-500" : "bg-emerald-500"}`}
                      style={{ width: `${Math.min(100, (spent / cap) * 100)}%` }}
                    />
                  </span>
                  of {money(data.spend.cap_usd, 2)} cap · {data.spend.calls_today} calls
                </span>
              }
              href="/trace"
            />
          </div>

          <div className="grid gap-6 lg:grid-cols-5">
            <div className="flex flex-col gap-3 lg:col-span-3">
              <div className="flex items-center justify-between">
                <h2 className="text-sm font-semibold uppercase tracking-wide text-zinc-500">Latest emails</h2>
                <Link href="/inbox" className="text-sm text-zinc-600 hover:text-zinc-900">
                  All emails →
                </Link>
              </div>
              {data.recent_emails.length ? (
                <EmailList emails={data.recent_emails} />
              ) : (
                <Empty title="No emails yet">
                  <Link href="/try" className="underline">Paste a buyer email</Link> to see the pipeline run.
                </Empty>
              )}
            </div>

            <div className="flex flex-col gap-6 lg:col-span-2">
              <Card title="High risks">
                {data.high_risks.length === 0 ? (
                  <p className="text-sm text-zinc-500">No high-risk findings.</p>
                ) : (
                  <ul className="flex flex-col gap-3">
                    {data.high_risks.map((risk, index) => (
                      <li key={index}>
                        <Link href={`/emails/${risk.email_id}`} className="group block">
                          <p className="text-sm font-medium group-hover:underline">
                            <span className="mr-2 rounded bg-red-100 px-1.5 py-0.5 text-xs font-medium text-red-800">
                              {CATEGORY_LABELS[risk.category] ?? risk.category}
                            </span>
                            {risk.po_number ? `PO ${risk.po_number}` : "PO pending"} · {risk.buyer}
                          </p>
                          <p className="mt-1 line-clamp-2 text-xs text-zinc-600">{risk.reason}</p>
                        </Link>
                      </li>
                    ))}
                  </ul>
                )}
              </Card>

              <Card title="How a demo email flows">
                <ol className="flex flex-col gap-2 text-sm text-zinc-700">
                  <li>
                    <b>1. Read.</b> Nemotron Nano classifies the email and extracts the PO; Python checks every field.
                  </li>
                  <li>
                    <b>2. Compare.</b> Python diffs it against the stored order and checks capacity and lead times.
                  </li>
                  <li>
                    <b>3. Judge.</b> Nemotron Super (Ultra when it matters) writes the risk findings, each with evidence.
                  </li>
                  <li>
                    <b>4. Reply.</b> Super drafts the reply; a fact check compares every number with the order.
                  </li>
                  <li>
                    <b>5. Ship.</b> After approval and the buyer&apos;s decision, Python builds the invoice and packing list.
                  </li>
                </ol>
                <Link href="/about" className="mt-3 inline-block text-sm text-sky-700 hover:underline">
                  How it works, with measured numbers →
                </Link>
              </Card>

              {data.demo_reset_enabled && (
                <Card title="Demo">
                  <p className="mb-3 text-sm text-zinc-600">
                    Someone else may have approved drafts or recorded decisions. Put the demo inbox back as it started.
                  </p>
                  <Button variant="secondary" onClick={reset} busy={resetting}>
                    Reset the demo
                  </Button>
                </Card>
              )}
            </div>
          </div>
        </>
      )}
    </Page>
  );
}

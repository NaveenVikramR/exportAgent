import Link from "next/link";
import type { ReactNode } from "react";
import { Card, Page, PageHeader } from "@/components/ui";

export const metadata = { title: "How it works · ExportAgent" };

// Measured numbers: backend/eval/REPORT.md (live runs on Nebius Token Factory, response cache off).
const DEV = { emails: 35, cost: "$0.0094", extraction: "$0.0004", risk: "$0.0060", drafting: "$0.0030", ultraRate: "21%", escalation: "30%", resolved: "91%" };

type Tone = "nano" | "super" | "ultra" | "python" | "human";

const TONES: Record<Tone, string> = {
  nano: "border-sky-300 bg-sky-50",
  super: "border-violet-300 bg-violet-50",
  ultra: "border-fuchsia-400 bg-fuchsia-50",
  python: "border-zinc-300 bg-white",
  human: "border-emerald-300 bg-emerald-50",
};

function Box({ tone, title, children }: { tone: Tone; title: string; children: ReactNode }) {
  return (
    <div className={`rounded-lg border-2 px-3 py-2 ${TONES[tone]}`}>
      <p className="text-sm font-semibold">{title}</p>
      <p className="text-xs text-zinc-600">{children}</p>
    </div>
  );
}

function Arrow({ label }: { label?: string }) {
  return (
    <div className="flex items-center justify-center gap-2 py-1 text-xs text-zinc-500">
      <span aria-hidden>↓</span>
      {label && <span>{label}</span>}
    </div>
  );
}

function Stage({ step, title, children }: { step: number; title: string; children: ReactNode }) {
  return (
    <div className="rounded-xl border border-zinc-200 bg-zinc-50 p-3">
      <p className="mb-2 text-xs font-semibold uppercase tracking-wide text-zinc-500">
        {step}. {title}
      </p>
      <div className="flex flex-col gap-2">{children}</div>
    </div>
  );
}

export default function About() {
  return (
    <Page wide>
      <PageHeader
        title="How it works"
        subtitle="Three NVIDIA Nemotron models on Nebius Token Factory, each used where it pays off, and Python wherever an answer can be computed."
      />

      <div className="grid gap-6 lg:grid-cols-5">
        <Card title="The pipeline and its model routing" className="lg:col-span-3">
          <div className="flex flex-col">
            <Stage step={1} title="Read">
              <Box tone="nano" title="Nemotron Nano: classify and extract">
                Every email. Category and intents, then every PO field with a confidence and the source quote.
              </Box>
              <Box tone="python" title="Python checks every field">
                Is the quote really in the email? Do sizes add up? Is a size table missing? Dates, revisions, colours normalised.
              </Box>
              <div className="ml-6 border-l-2 border-dashed border-violet-300 pl-3">
                <Box tone="super" title="Nemotron Super re-reads only the failing field">
                  {DEV.escalation} of emails; Super&apos;s answer is kept only if the same check then passes ({DEV.resolved} do).
                </Box>
              </div>
            </Stage>
            <Arrow />
            <Stage step={2} title="Compare">
              <Box tone="python" title="Python: match the order, diff the versions">
                Scored match on PO number, style, buyer and date; an unsure match becomes a question for a person.
              </Box>
            </Stage>
            <Arrow />
            <Stage step={3} title="Judge the risk">
              <Box tone="python" title="Python pre-fetch">Feasibility under the factory profile, value change, delivery options.</Box>
              <Box tone="super" title="Nemotron Super: the risk agent (default)">
                Tool-calling loop, at most 8 rounds: compliance and buyer checks (Tavily), what-if feasibility, the report.
              </Box>
              <div className="ml-6 border-l-2 border-dashed border-fuchsia-400 pl-3">
                <Box tone="ultra" title="Nemotron Ultra, when a trigger fires">
                  Infeasible plan · materials in-house or a partial shipment mentioned · Super contradicts the feasibility
                  check · Super&apos;s report invalid. {DEV.ultraRate} of risk runs.
                </Box>
              </div>
              <Box tone="python" title="Python flag policy">
                Every flag must cite real evidence; severity follows a fixed rubric. An unconfirmed date never makes a high flag.
              </Box>
            </Stage>
            <Arrow />
            <Stage step={4} title="Reply">
              <Box tone="super" title="Nemotron Super drafts the reply and an internal note">
                From the order data and findings only; thresholds and internal policy never reach the model.
              </Box>
              <Box tone="python" title="Python fact check">Every date, quantity and price in the draft is matched against the order and the email.</Box>
            </Stage>
            <Arrow />
            <Stage step={5} title="Approve and ship">
              <Box tone="human" title="A person approves, edits or rejects">Nothing is sent automatically.</Box>
              <Box tone="python" title="Python: Commercial Invoice and Packing List">
                From the agreed plan, one set per shipment; unknown values print as TO BE CONFIRMED.
              </Box>
            </Stage>
          </div>
        </Card>

        <div className="flex flex-col gap-6 lg:col-span-2">
          <Card title="Models">
            <table className="w-full text-left text-sm">
              <thead className="text-xs text-zinc-500">
                <tr>
                  <th className="py-1 font-medium">Model</th>
                  <th className="py-1 font-medium">Used for</th>
                </tr>
              </thead>
              <tbody className="align-top">
                <tr className="border-t border-zinc-100">
                  <td className="py-2 pr-2 font-medium">Nano 30B-A3B</td>
                  <td className="py-2 text-zinc-600">Classification, extraction, stated changes (thinking off)</td>
                </tr>
                <tr className="border-t border-zinc-100">
                  <td className="py-2 pr-2 font-medium">Super 120B-A12B</td>
                  <td className="py-2 text-zinc-600">Escalated fields, the risk agent, drafts</td>
                </tr>
                <tr className="border-t border-zinc-100">
                  <td className="py-2 pr-2 font-medium">Ultra 550B-A55B</td>
                  <td className="py-2 text-zinc-600">Risk runs that need it (triggers above)</td>
                </tr>
              </tbody>
            </table>
            <p className="mt-2 text-xs text-zinc-500">
              One router (backend/app/llm/router.py) logs every call: model, tokens, latency, cost. See{" "}
              <Link href="/trace" className="underline">Model calls</Link>.
            </p>
          </Card>

          <Card title={`Cost per email (DEV, ${DEV.emails} emails)`}>
            <dl className="grid grid-cols-2 gap-y-1.5 text-sm">
              <dt className="text-zinc-600">Read (Nano, Super on escalation)</dt>
              <dd className="text-right font-medium tabular-nums">{DEV.extraction}</dd>
              <dt className="text-zinc-600">Risk (Super, Ultra on triggers)</dt>
              <dd className="text-right font-medium tabular-nums">{DEV.risk}</dd>
              <dt className="text-zinc-600">Reply and note (Super)</dt>
              <dd className="text-right font-medium tabular-nums">{DEV.drafting}</dd>
              <dt className="border-t border-zinc-200 pt-1.5 font-medium">Total</dt>
              <dd className="border-t border-zinc-200 pt-1.5 text-right font-semibold tabular-nums">{DEV.cost}</dd>
            </dl>
            <p className="mt-2 text-xs text-zinc-500">
              Ultra for the risk step on every email cost $0.0215 per email on TEST v2; Super with escalation brought it to
              $0.0095 with the same high-risk recall.
            </p>
          </Card>

          <Card title="Evaluation">
            <table className="w-full text-sm">
              <thead className="text-xs text-zinc-500">
                <tr>
                  <th className="py-1 text-left font-medium" />
                  <th className="py-1 text-right font-medium">TEST v2 held out</th>
                  <th className="py-1 text-right font-medium">DEV</th>
                </tr>
              </thead>
              <tbody className="tabular-nums">
                {[
                  ["Field extraction", "96.5%", "98.7%"],
                  ["Right order matched", "98.7%", "100%"],
                  ["Changes found (recall)", "77.4%", "96.3%"],
                  ["High risks found (recall)", "100%", "100%"],
                  ["High-risk precision", "80.1%", "100%"],
                  ["Drafts passing the fact check", "97.1%", "97.1%"],
                ].map(([label, test, dev]) => (
                  <tr key={label} className="border-t border-zinc-100">
                    <td className="py-1.5 text-zinc-600">{label}</td>
                    <td className="py-1.5 text-right font-medium">{test}</td>
                    <td className="py-1.5 text-right">{dev}</td>
                  </tr>
                ))}
              </tbody>
            </table>
            <p className="mt-2 text-xs text-zinc-500">
              TEST v2: 30 emails written by a separate session from a spec alone, run 3× before any fix. DEV: 35 emails the
              system was built on. Regressions and failure analysis are in the evaluation report in the repository.
            </p>
          </Card>

          <Card title="Web checks (Tavily)">
            <p className="text-sm text-zinc-600">
              The risk agent may search for compliance rules for the product and destination, and for adverse news on the
              buyer. A compliance flag needs a concrete rule and a source URL; a buyer flag needs an adverse finding with a
              URL. Anything weaker is listed as checked, not flagged. Results are cached per query and day.
            </p>
          </Card>
        </div>
      </div>
    </Page>
  );
}

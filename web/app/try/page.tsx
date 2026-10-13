"use client";

import { useRouter } from "next/navigation";
import { useState } from "react";
import { Button, Card, ErrorBox, Notice, Page, PageHeader } from "@/components/ui";
import { api } from "@/lib/api";

const SAMPLES = [
  {
    label: "A new order",
    sender: "Lena Hartmann <lena@fjellsport.example>",
    subject: "New PO FS-2611 - merino base layers",
    body: `Hi Karthik,

Please book our PO FS-2611 for the merino-blend base layer FS-BL-04:
Graphite 1,200 pcs, Moss 800 pcs (2,000 pcs total)
Sizes S/M/L/XL, ratio 1:2:2:1
Price USD 9.40 per piece, FOB Chennai
Ex-factory 15 March 2027, shipping to our warehouse in Oslo, Norway.

Thanks,
Lena Hartmann
Fjellsport AS`,
  },
  {
    label: "A risky revision of a demo order",
    sender: "Anna Becker <a.becker@nordwind-mode.example>",
    subject: "NW-45120 Rev 2 - more Navy, earlier date",
    body: `Hi Karthik,

Revision 2 of NW-45120: please increase Navy to 8,000 pcs (White and Heather Grey unchanged) and bring the
ex-factory date forward to 20 November 2026. Price stays USD 4.85.

Best,
Anna Becker
Nordwind Mode GmbH`,
  },
];

export default function TryPage() {
  const router = useRouter();
  const [sender, setSender] = useState("");
  const [subject, setSubject] = useState("");
  const [body, setBody] = useState("");
  const [file, setFile] = useState<File | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function submit(event: React.FormEvent) {
    event.preventDefault();
    setBusy(true);
    setError(null);
    try {
      let email;
      if (file) {
        const form = new FormData();
        form.append("file", file);
        if (sender) form.append("sender", sender);
        if (subject) form.append("subject", subject);
        if (body) form.append("body", body);
        email = await api.uploadEmail(form);
      } else {
        email = await api.createEmail({ sender: sender || "Buyer <buyer@example.com>", subject: subject || "(no subject)", body });
      }
      router.push(`/emails/${email.id}?run=1`);
    } catch (err) {
      setError((err as Error).message);
      setBusy(false);
    }
  }

  const ready = file !== null || body.trim().length >= 10;

  return (
    <Page>
      <PageHeader
        title="Try your own email"
        subtitle="Paste a buyer email, or upload a PO as a PDF. ExportAgent analyses it, checks the risk and drafts a reply, live."
      />
      <Notice>
        Live runs use NVIDIA Nemotron on Nebius Token Factory and take about a minute. The public demo has a daily spend cap; when
        it is reached, the demo emails still work from their stored results. Please do not paste confidential data.
      </Notice>

      <Card>
        <div className="mb-4 flex flex-wrap items-center gap-2 text-sm">
          <span className="text-zinc-500">Fill in a sample:</span>
          {SAMPLES.map((sample) => (
            <button
              key={sample.label}
              type="button"
              onClick={() => {
                setSender(sample.sender);
                setSubject(sample.subject);
                setBody(sample.body);
                setFile(null);
              }}
              className="rounded-full border border-zinc-300 px-3 py-1 hover:bg-zinc-50"
            >
              {sample.label}
            </button>
          ))}
        </div>

        <form onSubmit={submit} className="flex flex-col gap-4">
          <div className="grid gap-4 md:grid-cols-2">
            <label className="flex flex-col gap-1 text-sm">
              <span className="font-medium">From</span>
              <input
                value={sender}
                onChange={(e) => setSender(e.target.value)}
                placeholder="Name <name@buyer.com>"
                className="rounded-md border border-zinc-300 px-3 py-2"
              />
            </label>
            <label className="flex flex-col gap-1 text-sm">
              <span className="font-medium">Subject</span>
              <input
                value={subject}
                onChange={(e) => setSubject(e.target.value)}
                placeholder="New PO 4471"
                className="rounded-md border border-zinc-300 px-3 py-2"
              />
            </label>
          </div>
          <label className="flex flex-col gap-1 text-sm">
            <span className="font-medium">Email body {file && <span className="font-normal text-zinc-500">(optional with a PDF)</span>}</span>
            <textarea
              value={body}
              onChange={(e) => setBody(e.target.value)}
              rows={12}
              placeholder="Paste the buyer's email here, including any order details or quoted thread."
              className="rounded-md border border-zinc-300 px-3 py-2 font-mono text-sm"
            />
          </label>
          <label className="flex flex-col gap-1 text-sm">
            <span className="font-medium">PO as a PDF (optional)</span>
            <input
              type="file"
              accept="application/pdf"
              onChange={(e) => setFile(e.target.files?.[0] ?? null)}
              className="text-sm file:mr-3 file:rounded-md file:border file:border-zinc-300 file:bg-white file:px-3 file:py-1.5"
            />
            <span className="text-xs text-zinc-500">
              PDFs with a text layer, up to 5 MB. Scanned images are not supported yet.
            </span>
          </label>
          {error && <ErrorBox>{error}</ErrorBox>}
          <div>
            <Button type="submit" busy={busy} disabled={!ready}>
              {busy ? "Sending…" : "Analyse this email"}
            </Button>
          </div>
        </form>
      </Card>
    </Page>
  );
}

"use client";

import Link from "next/link";
import { useCallback, useEffect, useState } from "react";
import { EmailList } from "@/components/email-list";
import { Empty, ErrorBox, Loading, Page, PageHeader } from "@/components/ui";
import { api, type EmailSummary } from "@/lib/api";

export default function Inbox() {
  const [emails, setEmails] = useState<EmailSummary[] | null>(null);
  const [error, setError] = useState<string | null>(null);

  const load = useCallback(() => {
    api
      .emails()
      .then(setEmails)
      .catch((err: Error) => setError(err.message));
  }, []);
  useEffect(load, [load]);
  const retry = () => {
    setError(null);
    load();
  };

  return (
    <Page>
      <PageHeader
        title="Inbox"
        subtitle="Buyer emails, classified and checked before anyone replies."
        actions={
          <Link href="/try" className="rounded-md bg-zinc-900 px-3 py-1.5 text-sm font-medium text-white hover:bg-zinc-700">
            Try your own email
          </Link>
        }
      />
      {error && <ErrorBox retry={retry}>Could not load the inbox: {error}</ErrorBox>}
      {!emails && !error && <Loading />}
      {emails?.length === 0 && (
        <Empty title="No emails yet">
          Paste one on <Link href="/try" className="underline">Try your own email</Link>, or load the demo with{" "}
          <code className="font-mono">python -m scripts.load_demo</code>.
        </Empty>
      )}
      {emails && emails.length > 0 && <EmailList emails={emails} />}
    </Page>
  );
}

import Link from "next/link";
import { CategoryBadge, StatusBadge } from "@/components/badges";
import type { EmailSummary } from "@/lib/api";

export function EmailList({ emails }: { emails: EmailSummary[] }) {
  return (
    <ul className="divide-y divide-zinc-100 overflow-hidden rounded-xl border border-zinc-200 bg-white shadow-sm">
      {emails.map((email) => (
        <li key={email.id}>
          <Link href={`/emails/${email.id}`} className="flex items-start gap-4 px-5 py-4 hover:bg-zinc-50">
            <div className="min-w-0 flex-1">
              <p className="truncate text-sm font-medium">{email.subject}</p>
              <p className="truncate text-sm text-zinc-500">{email.sender}</p>
              {email.classification && <p className="mt-1 line-clamp-2 text-sm text-zinc-600">{email.classification.summary}</p>}
            </div>
            <div className="flex shrink-0 flex-col items-end gap-1.5">
              <span className="text-xs text-zinc-500">
                {new Date(email.received_at).toLocaleDateString("en-GB", { day: "numeric", month: "short", year: "numeric" })}
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
  );
}

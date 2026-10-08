"use client";

import Link from "next/link";
import { useParams } from "next/navigation";
import { useEffect, useState } from "react";
import { ALERT_LABELS, AlertBadge } from "@/components/badges";
import { api, type Change, type OrderDetail, type POVersion, type ScalarField } from "@/lib/api";

const FIELDS: [ScalarField, string][] = [
  ["buyer", "Buyer"],
  ["style", "Style"],
  ["currency", "Currency"],
  ["unit_price", "Unit price"],
  ["total_quantity", "Total quantity"],
  ["delivery_date", "Delivery date"],
  ["incoterms", "Incoterms"],
  ["port", "Port"],
  ["destination_country", "Destination"],
];

const KIND_LABELS: Record<Change["kind"], string> = {
  quantity: "Quantity",
  price: "Price",
  delivery_date: "Delivery date",
  size_ratio: "Size ratio",
  colour: "Colour",
  incoterms: "Incoterms",
  other: "Other",
};

function formatValue(value: unknown): string {
  if (value === null || value === undefined) return "–";
  if (typeof value === "number") return value.toLocaleString("en-US");
  if (typeof value === "object") {
    return Object.entries(value as Record<string, number>)
      .map(([size, qty]) => `${size} ${qty.toLocaleString("en-US")}`)
      .join(" · ");
  }
  return String(value);
}

function fieldLabel(field: string): string {
  if (field.startsWith("line_items.")) {
    const [, colour, part] = field.split(".");
    return part ? `${colour} · ${part === "sizes" ? "sizes" : part.replace("_", " ")}` : colour;
  }
  return FIELDS.find(([name]) => name === field)?.[1] ?? field;
}

function ChangeRow({ change }: { change: Change }) {
  return (
    <li className={`rounded border px-3 py-2 ${change.alert ? "border-red-200 bg-red-50" : "border-zinc-200"}`}>
      <div className="flex flex-wrap items-center gap-2 text-sm">
        <span className="w-32 shrink-0 text-xs uppercase tracking-wide text-zinc-500">{KIND_LABELS[change.kind]}</span>
        <span className="font-medium">{fieldLabel(change.field)}</span>
        <span className="rounded bg-red-100 px-1.5 py-0.5 font-mono text-xs text-red-800 line-through">
          {formatValue(change.old)}
        </span>
        <span className="text-zinc-400">→</span>
        <span className="rounded bg-emerald-100 px-1.5 py-0.5 font-mono text-xs text-emerald-800">
          {formatValue(change.new)}
        </span>
        {change.alert && <AlertBadge alert={change.alert} />}
      </div>
      <p className="mt-1 text-xs text-zinc-600 sm:pl-34">{change.detail}</p>
    </li>
  );
}

function VersionEntry({ version, isCurrent }: { version: POVersion; isCurrent: boolean }) {
  const changes = version.changes ?? [];
  return (
    <li className="relative pl-6">
      <span
        className={`absolute -left-1.5 top-1.5 h-3 w-3 rounded-full border-2 ${
          changes.some((c) => c.alert) ? "border-red-500 bg-red-100" : "border-zinc-400 bg-white"
        }`}
      />
      <div className="flex flex-wrap items-baseline gap-x-3 gap-y-1">
        <h3 className="font-semibold">Version {version.version}</h3>
        {isCurrent && <span className="text-xs font-medium text-emerald-700">current</span>}
        <span className="text-xs text-zinc-500">
          {new Date(version.created_at).toLocaleString("en-GB", { dateStyle: "medium", timeStyle: "short" })}
        </span>
        {version.email_id && (
          <Link href={`/emails/${version.email_id}`} className="text-xs text-sky-700 hover:underline">
            Source email
          </Link>
        )}
      </div>
      {version.basis === "thread_reference" && (
        <p className="mt-1 text-sm text-zinc-600">
          Rebuilt from earlier values quoted in the buyer&apos;s reply thread; we had no copy of this version.
        </p>
      )}
      {changes.length === 0 && version.basis === "document" && version.version === 1 && (
        <p className="mt-1 text-sm text-zinc-600">Order created.</p>
      )}
      {changes.length > 0 && (
        <ul className="mt-2 flex flex-col gap-1.5">
          {changes.map((change) => (
            <ChangeRow key={change.field} change={change} />
          ))}
        </ul>
      )}
    </li>
  );
}

export default function OrderPage() {
  const { id } = useParams<{ id: string }>();
  const [order, setOrder] = useState<OrderDetail | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    api
      .order(id)
      .then(setOrder)
      .catch((err: Error) => setError(err.message));
  }, [id]);

  const current = order?.versions[0]?.data;
  const sizes = current ? Array.from(new Set(current.line_items.flatMap((item) => Object.keys(item.sizes)))) : [];

  return (
    <main className="mx-auto flex w-full max-w-5xl flex-col gap-6 px-6 py-10">
      <Link href="/orders" className="text-sm text-zinc-600 hover:text-zinc-900">
        ← Orders
      </Link>

      {error && (
        <div className="rounded-lg border border-red-200 bg-red-50 p-4 text-sm text-red-800">{error}</div>
      )}
      {!order && !error && <p className="text-sm text-zinc-500">Loading…</p>}

      {order && current && (
        <>
          <header className="flex flex-wrap items-start justify-between gap-3">
            <div>
              <h1 className="text-xl font-semibold">PO {order.po_number}</h1>
              <p className="text-sm text-zinc-600">
                {order.buyer} · version {order.current_version}
              </p>
            </div>
            <div className="flex gap-1.5">
              {order.alerts.map((alert) => (
                <AlertBadge key={alert} alert={alert} />
              ))}
            </div>
          </header>

          {order.alerts.includes("delivery_pulled_forward") && (
            <p className="rounded border border-red-200 bg-red-50 px-3 py-2 text-sm text-red-900">
              {ALERT_LABELS.delivery_pulled_forward}: the latest version leaves less production time than the
              previous one. Check capacity before confirming.
            </p>
          )}

          <section className="rounded-lg border border-zinc-200 bg-white p-5">
            <h2 className="mb-3 text-sm font-semibold uppercase tracking-wide text-zinc-500">Current order</h2>
            <dl className="grid grid-cols-1 gap-x-6 gap-y-2 text-sm sm:grid-cols-3">
              {FIELDS.map(([name, label]) => (
                <div key={name}>
                  <dt className="text-xs text-zinc-500">{label}</dt>
                  <dd className="font-medium">{formatValue(current[name])}</dd>
                </div>
              ))}
            </dl>
            {current.line_items.length > 0 && (
              <div className="mt-5 overflow-x-auto">
                <table className="w-full text-left text-sm">
                  <thead className="text-zinc-500">
                    <tr>
                      <th className="py-1 font-medium">Colour</th>
                      {sizes.map((size) => (
                        <th key={size} className="py-1 text-right font-medium">
                          {size}
                        </th>
                      ))}
                      <th className="py-1 text-right font-medium">Quantity</th>
                    </tr>
                  </thead>
                  <tbody>
                    {current.line_items.map((item, index) => (
                      <tr key={index} className="border-t border-zinc-100">
                        <td className="py-1.5">{item.colour}</td>
                        {sizes.map((size) => (
                          <td key={size} className="py-1.5 text-right tabular-nums">
                            {item.sizes[size]?.toLocaleString("en-US") ?? ""}
                          </td>
                        ))}
                        <td className="py-1.5 text-right font-medium tabular-nums">
                          {item.quantity?.toLocaleString("en-US")}
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            )}
          </section>

          <section className="rounded-lg border border-zinc-200 bg-white p-5">
            <h2 className="mb-4 text-sm font-semibold uppercase tracking-wide text-zinc-500">Version history</h2>
            <ol className="flex flex-col gap-6 border-l border-zinc-200 pl-0">
              {order.versions.map((version, index) => (
                <VersionEntry key={version.id} version={version} isCurrent={index === 0} />
              ))}
            </ol>
          </section>
        </>
      )}
    </main>
  );
}

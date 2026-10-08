"use client";

import Link from "next/link";
import { useEffect, useState } from "react";
import { AlertBadge } from "@/components/badges";
import { api, type OrderSummary } from "@/lib/api";

export default function Orders() {
  const [orders, setOrders] = useState<OrderSummary[] | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    api
      .orders()
      .then(setOrders)
      .catch((err: Error) => setError(err.message));
  }, []);

  return (
    <main className="mx-auto flex w-full max-w-5xl flex-col gap-6 px-6 py-10">
      <header>
        <h1 className="text-2xl font-semibold">Orders</h1>
        <p className="text-sm text-zinc-600">
          Every PO version is kept. Orders whose latest version changed something are marked.
        </p>
      </header>

      {error && (
        <div className="rounded-lg border border-red-200 bg-red-50 p-4 text-sm text-red-800">
          Could not load orders: {error}
        </div>
      )}
      {!orders && !error && <p className="text-sm text-zinc-500">Loading…</p>}
      {orders?.length === 0 && (
        <p className="text-sm text-zinc-500">No orders yet. Analyse an email that carries a PO.</p>
      )}

      {orders && orders.length > 0 && (
        <div className="overflow-x-auto rounded-lg border border-zinc-200 bg-white">
          <table className="w-full text-left text-sm">
            <thead className="bg-zinc-50 text-zinc-500">
              <tr>
                <th className="px-4 py-2 font-medium">PO number</th>
                <th className="px-4 py-2 font-medium">Buyer</th>
                <th className="px-4 py-2 font-medium">Style</th>
                <th className="px-4 py-2 text-right font-medium">Version</th>
                <th className="px-4 py-2 font-medium">Latest change</th>
              </tr>
            </thead>
            <tbody>
              {orders.map((order) => (
                <tr key={order.id} className="border-t border-zinc-100 hover:bg-zinc-50">
                  <td className="px-4 py-2.5 font-medium">
                    <Link href={`/orders/${order.id}`} className="hover:underline">
                      {order.po_number}
                    </Link>
                  </td>
                  <td className="px-4 py-2.5">{order.buyer}</td>
                  <td className="px-4 py-2.5 font-mono text-xs">{order.style ?? "–"}</td>
                  <td className="px-4 py-2.5 text-right tabular-nums">v{order.current_version}</td>
                  <td className="px-4 py-2.5">
                    <div className="flex flex-wrap items-center gap-1.5">
                      {order.alerts.map((alert) => (
                        <AlertBadge key={alert} alert={alert} />
                      ))}
                      <span className="text-xs text-zinc-500">
                        {order.latest_change_count > 0
                          ? `${order.latest_change_count} ${order.latest_change_count === 1 ? "change" : "changes"}`
                          : "New order"}
                      </span>
                    </div>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </main>
  );
}

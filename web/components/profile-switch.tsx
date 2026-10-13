"use client";

import { useCallback, useEffect, useState } from "react";
import { Button, Card, ErrorBox, Loading } from "@/components/ui";
import { api, type ProfileComparison } from "@/lib/api";

const VERDICT_STYLES: Record<string, string> = {
  feasible: "bg-emerald-100 text-emerald-800",
  tight: "bg-amber-100 text-amber-800",
  infeasible: "bg-red-100 text-red-800",
};

// The same order under each factory/country profile: capacity, fabric lead time and the invoice
// header differ; the feasibility check is the same Python the risk agent uses.
export function ProfileSwitch({ orderId, active, onSwitched }: { orderId: number; active: string; onSwitched: () => void }) {
  const [rows, setRows] = useState<ProfileComparison[] | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState<string | null>(null);

  const load = useCallback(() => {
    api
      .compareProfiles(String(orderId))
      .then(setRows)
      .catch((err: Error) => setError(err.message));
  }, [orderId]);
  useEffect(load, [load]);

  async function choose(profile: string) {
    setBusy(profile);
    setError(null);
    try {
      await api.setProfile(orderId, profile);
      onSwitched();
    } catch (err) {
      setError((err as Error).message);
    } finally {
      setBusy(null);
    }
  }

  return (
    <Card title="Factory profile">
      <p className="mb-4 text-sm text-zinc-600">
        Everything country- or factory-specific lives in a profile: capacity, fabric lead time, port and the invoice format.
        The same order, checked against each one:
      </p>
      {error && <ErrorBox>{error}</ErrorBox>}
      {!rows && !error && <Loading />}
      {rows && (
        <div className="grid gap-4 md:grid-cols-2">
          {rows.map(({ profile, feasibility, invoice }) => {
            const isActive = profile.id === active;
            return (
              <div
                key={profile.id}
                className={`flex flex-col gap-3 rounded-lg border p-4 ${isActive ? "border-zinc-900 ring-1 ring-zinc-900" : "border-zinc-200"}`}
              >
                <div className="flex items-start justify-between gap-2">
                  <div>
                    <p className="font-medium">
                      {profile.city}, {profile.country}
                    </p>
                    <p className="text-xs text-zinc-500">
                      {profile.factory} · {profile.free_pcs_per_week.toLocaleString("en-US")} pcs/week free · fabric{" "}
                      {profile.fabric_days} days
                    </p>
                  </div>
                  {isActive ? (
                    <span className="rounded bg-zinc-900 px-2 py-0.5 text-xs font-medium text-white">In use</span>
                  ) : (
                    <Button variant="secondary" onClick={() => choose(profile.id)} busy={busy === profile.id}>
                      Use this profile
                    </Button>
                  )}
                </div>
                {feasibility ? (
                  <div>
                    <span className={`rounded px-2 py-0.5 text-xs font-semibold uppercase ${VERDICT_STYLES[feasibility.verdict] ?? ""}`}>
                      {feasibility.verdict}
                    </span>
                    <p className="mt-1.5 text-sm text-zinc-700">{feasibility.reason}</p>
                  </div>
                ) : (
                  <p className="text-sm text-zinc-500">No delivery date and quantity yet: nothing to check.</p>
                )}
                <dl className="grid grid-cols-2 gap-x-3 gap-y-1 border-t border-zinc-100 pt-3 text-xs">
                  <dt className="text-zinc-500">Exporter</dt>
                  <dd>{invoice.exporter_name}</dd>
                  <dt className="text-zinc-500">Country of origin</dt>
                  <dd>{invoice.country_of_origin}</dd>
                  <dt className="text-zinc-500">Port of loading</dt>
                  <dd>{invoice.port_of_loading}</dd>
                  <dt className="text-zinc-500">Invoice number</dt>
                  <dd className="font-mono">{invoice.invoice_prefix}…</dd>
                  <dt className="text-zinc-500">Registrations</dt>
                  <dd>{Object.keys(invoice.registration).join(", ")}</dd>
                </dl>
              </div>
            );
          })}
        </div>
      )}
      <p className="mt-3 text-xs text-zinc-500">
        Switching changes the profile used for new risk assessments and documents of this order.
      </p>
    </Card>
  );
}

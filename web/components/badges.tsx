const STATUS_STYLES: Record<string, string> = {
  new: "bg-zinc-100 text-zinc-700",
  analysed: "bg-emerald-100 text-emerald-800",
  needs_review: "bg-amber-100 text-amber-900",
  failed: "bg-red-100 text-red-800",
};

const STATUS_LABELS: Record<string, string> = {
  new: "New",
  analysed: "Analysed",
  needs_review: "Needs review",
  failed: "Failed",
};

export const CATEGORY_LABELS: Record<string, string> = {
  new_po: "New PO",
  po_revision: "PO revision",
  delivery_change: "Delivery change",
  order_query: "Order query",
  sample_or_approval: "Samples / approvals",
  shipment_docs: "Shipping documents",
  payment: "Payment",
  other: "Other",
};

export const ALERT_LABELS: Record<string, string> = {
  delivery_pulled_forward: "Delivery pulled forward",
};

export function AlertBadge({ alert }: { alert: string }) {
  return (
    <span className="whitespace-nowrap rounded bg-red-100 px-2 py-0.5 text-xs font-medium text-red-800">
      {ALERT_LABELS[alert] ?? alert}
    </span>
  );
}

export function StatusBadge({ status }: { status: string }) {
  return (
    <span
      className={`whitespace-nowrap rounded px-2 py-0.5 text-xs font-medium ${STATUS_STYLES[status] ?? STATUS_STYLES.new}`}
    >
      {STATUS_LABELS[status] ?? status}
    </span>
  );
}

export function CategoryBadge({ category }: { category: string }) {
  return (
    <span className="whitespace-nowrap rounded border border-zinc-200 bg-white px-2 py-0.5 text-xs text-zinc-700">
      {CATEGORY_LABELS[category] ?? category}
    </span>
  );
}

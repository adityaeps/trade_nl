"use client";

import { useCallback, useEffect, useState } from "react";
import {
  listQuotes,
  quoteStatusCounts,
  updateQuoteStatus,
  type AdminQuote,
} from "@/lib/adminApi";
import { formatEur } from "@/lib/pricing";

// Mirrors ALLOWED_TRANSITIONS in app/api/v1/admin/quotes.py. The server is
// the authority and rejects anything else with a 409 - this only decides
// which buttons to render, so staff aren't offered actions that will fail.
const NEXT_STATUSES: Record<string, { value: string; label: string }[]> = {
  confirmed: [
    { value: "inspected", label: "Mark inspected" },
    { value: "rejected", label: "Reject" },
  ],
  inspected: [
    { value: "paid", label: "Mark paid" },
    { value: "rejected", label: "Reject" },
  ],
  manual_review: [
    { value: "confirmed", label: "Approve" },
    { value: "rejected", label: "Reject" },
  ],
};

const STATUS_STYLES: Record<string, string> = {
  pending: "bg-gray-100 text-gray-600",
  confirmed: "bg-blue-50 text-blue-700",
  inspected: "bg-violet-50 text-violet-700",
  paid: "bg-emerald-50 text-emerald-700",
  manual_review: "bg-amber-50 text-amber-700",
  rejected: "bg-red-50 text-red-700",
  expired: "bg-gray-100 text-gray-400",
};

const FILTERS = [
  { value: "", label: "All" },
  { value: "pending", label: "Pending" },
  { value: "confirmed", label: "Confirmed" },
  { value: "manual_review", label: "Manual review" },
  { value: "inspected", label: "Inspected" },
  { value: "paid", label: "Paid" },
  { value: "rejected", label: "Rejected" },
];

export default function OrdersPage() {
  const [quotes, setQuotes] = useState<AdminQuote[]>([]);
  const [counts, setCounts] = useState<Record<string, number>>({});
  const [filter, setFilter] = useState("");
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [busyId, setBusyId] = useState<string | null>(null);

  const load = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const [rows, c] = await Promise.all([
        listQuotes(filter || undefined),
        quoteStatusCounts(),
      ]);
      setQuotes(rows);
      setCounts(c.by_status);
    } catch (e: any) {
      setError(e.message);
    } finally {
      setLoading(false);
    }
  }, [filter]);

  useEffect(() => {
    load();
  }, [load]);

  async function transition(quote: AdminQuote, status: string) {
    setBusyId(quote.id);
    setError(null);
    try {
      await updateQuoteStatus(quote.id, { status });
      await load();
    } catch (e: any) {
      setError(e.message);
    } finally {
      setBusyId(null);
    }
  }

  return (
    <main className="mx-auto max-w-6xl px-4 py-8 sm:px-6">
      <h1 className="text-2xl font-bold tracking-tight text-gray-900">Orders</h1>
      <p className="mt-1 text-sm text-gray-500">
        Quotes across every status. Transitions follow the lifecycle in
        ARCHITECTURE.md §5 — the server rejects anything out of order.
      </p>

      <div className="mt-5 flex flex-wrap gap-2">
        {FILTERS.map((f) => (
          <button
            key={f.value}
            onClick={() => setFilter(f.value)}
            className={`rounded-lg px-3 py-1.5 text-sm font-medium transition ${
              filter === f.value
                ? "bg-gray-900 text-white"
                : "bg-white text-gray-600 hover:bg-gray-100"
            }`}
          >
            {f.label}
            {f.value && counts[f.value] !== undefined && (
              <span
                className={`ml-1.5 text-xs ${
                  filter === f.value ? "text-gray-300" : "text-gray-400"
                }`}
              >
                {counts[f.value]}
              </span>
            )}
          </button>
        ))}
      </div>

      {error && (
        <p className="mt-4 rounded-xl bg-red-50 px-4 py-3 text-sm text-red-700">{error}</p>
      )}

      {loading ? (
        <div className="mt-6 space-y-2">
          {Array.from({ length: 5 }).map((_, i) => (
            <div key={i} className="h-16 animate-pulse rounded-xl bg-gray-100" />
          ))}
        </div>
      ) : quotes.length === 0 ? (
        <p className="mt-10 text-center text-sm text-gray-500">No quotes with this status.</p>
      ) : (
        <div className="mt-6 overflow-hidden rounded-2xl border border-gray-200 bg-white shadow-card">
          <table className="w-full text-sm">
            <thead className="bg-gray-50 text-left text-xs font-semibold uppercase tracking-wide text-gray-500">
              <tr>
                <th className="px-4 py-3">Device</th>
                <th className="px-4 py-3">Customer</th>
                <th className="px-4 py-3">Price</th>
                <th className="px-4 py-3">Fulfilment</th>
                <th className="px-4 py-3">Status</th>
                <th className="px-4 py-3" />
              </tr>
            </thead>
            <tbody className="divide-y divide-gray-100">
              {quotes.map((q) => (
                <tr key={q.id} className="hover:bg-gray-50/60">
                  <td className="px-4 py-3">
                    <div className="font-medium text-gray-900">{q.device_label}</div>
                    <div className="font-mono text-[11px] text-gray-400">
                      {q.id.slice(0, 8)}
                    </div>
                  </td>
                  <td className="px-4 py-3">
                    {q.customer_name ? (
                      <>
                        <div className="text-gray-900">{q.customer_name}</div>
                        <div className="text-xs text-gray-500">{q.customer_email}</div>
                      </>
                    ) : (
                      <span className="text-gray-400">— not confirmed</span>
                    )}
                  </td>
                  <td className="px-4 py-3 font-semibold text-emerald-700">
                    {q.calculated_price ? formatEur(q.calculated_price) : "—"}
                  </td>
                  <td className="px-4 py-3 text-gray-600">
                    {q.fulfillment_method === "store"
                      ? q.store_name ?? "Store"
                      : q.fulfillment_method === "courier"
                        ? "Courier"
                        : "—"}
                  </td>
                  <td className="px-4 py-3">
                    <span
                      className={`rounded-full px-2 py-0.5 text-xs font-medium ${
                        STATUS_STYLES[q.status] ?? "bg-gray-100 text-gray-600"
                      }`}
                    >
                      {q.status.replace("_", " ")}
                    </span>
                  </td>
                  <td className="px-4 py-3 text-right">
                    <div className="flex justify-end gap-1.5">
                      {(NEXT_STATUSES[q.status] ?? []).map((action) => (
                        <button
                          key={action.value}
                          disabled={busyId === q.id}
                          onClick={() => transition(q, action.value)}
                          className={`rounded-lg border px-2.5 py-1 text-xs font-medium transition disabled:opacity-50 ${
                            action.value === "rejected"
                              ? "border-red-200 text-red-600 hover:bg-red-50"
                              : "border-gray-200 text-gray-700 hover:border-gray-400"
                          }`}
                        >
                          {action.label}
                        </button>
                      ))}
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

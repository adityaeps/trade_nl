"use client";

import { useCallback, useEffect, useState } from "react";
import {
  downloadPayoutCsv,
  listPayouts,
  markPayoutPaid,
  type Payout,
} from "@/lib/adminApi";
import { formatEur } from "@/lib/pricing";

const FILTERS = [
  { value: "pending", label: "Pending" },
  { value: "paid", label: "Paid" },
  { value: "", label: "All" },
];

/** IBANs are grouped in 4s for readability - the same way banks print them. */
function formatIban(iban: string) {
  return iban.replace(/(.{4})/g, "$1 ").trim();
}

export default function PayoutsPage() {
  const [payouts, setPayouts] = useState<Payout[]>([]);
  const [filter, setFilter] = useState("pending");
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [busyId, setBusyId] = useState<number | null>(null);
  const [revealed, setRevealed] = useState<Set<number>>(new Set());

  const load = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      setPayouts(await listPayouts(filter || undefined));
    } catch (e: any) {
      setError(e.message);
    } finally {
      setLoading(false);
    }
  }, [filter]);

  useEffect(() => {
    load();
  }, [load]);

  async function confirmPaid(payout: Payout) {
    // Money movement happens outside this system (§2 - manual bank
    // transfer), so this is recording a fact, not performing one. Confirm
    // explicitly: it's effectively irreversible bookkeeping.
    const ok = window.confirm(
      `Mark ${formatEur(payout.amount)} to ${payout.account_holder_name} as paid?\n\n` +
        `This only records that you have transferred it in your bank — it does not move money.`
    );
    if (!ok) return;

    setBusyId(payout.id);
    setError(null);
    try {
      await markPayoutPaid(payout.id);
      await load();
    } catch (e: any) {
      setError(e.message);
    } finally {
      setBusyId(null);
    }
  }

  const pendingTotal = payouts
    .filter((p) => p.status === "pending")
    .reduce((sum, p) => sum + Number(p.amount), 0);

  return (
    <main className="mx-auto max-w-6xl px-4 py-8 sm:px-6">
      <div className="flex flex-wrap items-start justify-between gap-4">
        <div>
          <h1 className="text-2xl font-bold tracking-tight text-gray-900">Payouts</h1>
          <p className="mt-1 text-sm text-gray-500">
            Bank transfers are made manually (§2). This queue tracks what is owed
            and what has been sent.
          </p>
        </div>
        <button
          onClick={() => downloadPayoutCsv(filter || "pending").catch((e) => setError(e.message))}
          className="rounded-xl bg-gray-900 px-4 py-2 text-sm font-semibold text-white transition hover:bg-gray-700"
        >
          Export CSV
        </button>
      </div>

      <div className="mt-5 flex flex-wrap items-center gap-2">
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
          </button>
        ))}
        {filter === "pending" && payouts.length > 0 && (
          <span className="ml-auto text-sm text-gray-500">
            {payouts.length} pending ·{" "}
            <span className="font-semibold text-gray-900">{formatEur(pendingTotal)}</span> total
          </span>
        )}
      </div>

      {error && (
        <p className="mt-4 rounded-xl bg-red-50 px-4 py-3 text-sm text-red-700">{error}</p>
      )}

      {loading ? (
        <div className="mt-6 space-y-2">
          {Array.from({ length: 4 }).map((_, i) => (
            <div key={i} className="h-16 animate-pulse rounded-xl bg-gray-100" />
          ))}
        </div>
      ) : payouts.length === 0 ? (
        <p className="mt-10 text-center text-sm text-gray-500">
          Nothing in this queue.
        </p>
      ) : (
        <div className="mt-6 overflow-hidden rounded-2xl border border-gray-200 bg-white shadow-card">
          <table className="w-full text-sm">
            <thead className="bg-gray-50 text-left text-xs font-semibold uppercase tracking-wide text-gray-500">
              <tr>
                <th className="px-4 py-3">Account holder</th>
                <th className="px-4 py-3">IBAN</th>
                <th className="px-4 py-3">Amount</th>
                <th className="px-4 py-3">Status</th>
                <th className="px-4 py-3" />
              </tr>
            </thead>
            <tbody className="divide-y divide-gray-100">
              {payouts.map((p) => (
                <tr key={p.id} className="hover:bg-gray-50/60">
                  <td className="px-4 py-3">
                    <div className="font-medium text-gray-900">{p.account_holder_name}</div>
                    <div className="text-xs text-gray-500">{p.customer_email}</div>
                  </td>
                  <td className="px-4 py-3">
                    {/* Masked by default: this is the one screen showing
                        decrypted IBANs, and it's often open on a shared
                        screen. Click to reveal a single row. */}
                    {revealed.has(p.id) ? (
                      <span className="font-mono text-xs text-gray-800">
                        {formatIban(p.iban)}
                      </span>
                    ) : (
                      <button
                        onClick={() => setRevealed((s) => new Set(s).add(p.id))}
                        className="font-mono text-xs text-gray-400 underline decoration-dotted hover:text-gray-700"
                      >
                        •••• {p.iban.slice(-4)} — reveal
                      </button>
                    )}
                  </td>
                  <td className="px-4 py-3 font-semibold text-gray-900">
                    {formatEur(p.amount)}
                  </td>
                  <td className="px-4 py-3">
                    <span
                      className={`rounded-full px-2 py-0.5 text-xs font-medium ${
                        p.status === "paid"
                          ? "bg-emerald-50 text-emerald-700"
                          : "bg-amber-50 text-amber-700"
                      }`}
                    >
                      {p.status}
                    </span>
                    {p.paid_at && (
                      <div className="mt-0.5 text-[11px] text-gray-400">
                        {new Date(p.paid_at).toLocaleDateString()}
                      </div>
                    )}
                  </td>
                  <td className="px-4 py-3 text-right">
                    {p.status === "pending" && (
                      <button
                        disabled={busyId === p.id}
                        onClick={() => confirmPaid(p)}
                        className="rounded-lg border border-gray-200 px-2.5 py-1 text-xs font-medium text-gray-700 transition hover:border-gray-400 disabled:opacity-50"
                      >
                        {busyId === p.id ? "Saving…" : "Mark paid"}
                      </button>
                    )}
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

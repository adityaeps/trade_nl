"use client";

import { useCallback, useEffect, useState } from "react";
import { listDevices, updateBasePrice, type AdminDevice } from "@/lib/adminApi";
import { AlertTriangleIcon, SearchIcon } from "@/lib/icons";

const TIERS = ["high", "medium", "low"];

function PriceRow({
  device,
  onSaved,
}: {
  device: AdminDevice;
  onSaved: (d: AdminDevice) => void;
}) {
  const [price, setPrice] = useState(device.base_price ?? "");
  const [markup, setMarkup] = useState(device.markup_pct ?? "0");
  const [tier, setTier] = useState(device.liquidity_tier ?? "medium");
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [savedAt, setSavedAt] = useState<number | null>(null);

  const dirty =
    price !== (device.base_price ?? "") ||
    markup !== (device.markup_pct ?? "0") ||
    tier !== (device.liquidity_tier ?? "medium");

  async function save() {
    setSaving(true);
    setError(null);
    try {
      const updated = await updateBasePrice(device.id, {
        base_price: price,
        markup_pct: markup,
        liquidity_tier: tier,
      });
      onSaved(updated);
      setSavedAt(Date.now());
    } catch (e: any) {
      setError(e.message);
    } finally {
      setSaving(false);
    }
  }

  return (
    <tr className={saving ? "opacity-50" : ""}>
      <td className="px-4 py-3">
        <div className="font-medium text-gray-900">{device.model}</div>
        <div className="text-xs text-gray-400">
          {device.brand} · {device.storage_gb}GB
        </div>
        {error && <div className="mt-1 text-xs text-red-600">{error}</div>}
      </td>
      <td className="px-4 py-3">
        <div className="flex items-center gap-1">
          <span className="text-gray-400">€</span>
          <input
            value={price}
            onChange={(e) => setPrice(e.target.value)}
            inputMode="decimal"
            className="w-24 rounded-lg border border-gray-200 px-2 py-1.5 text-sm tabular-nums focus:border-brand-400 focus:outline-none focus:ring-2 focus:ring-brand-100"
          />
        </div>
      </td>
      <td className="px-4 py-3">
        <div className="flex items-center gap-1">
          <input
            value={markup}
            onChange={(e) => setMarkup(e.target.value)}
            inputMode="decimal"
            className="w-16 rounded-lg border border-gray-200 px-2 py-1.5 text-sm tabular-nums focus:border-brand-400 focus:outline-none focus:ring-2 focus:ring-brand-100"
          />
          <span className="text-gray-400">%</span>
        </div>
      </td>
      <td className="px-4 py-3">
        <select
          value={tier}
          onChange={(e) => setTier(e.target.value)}
          className="rounded-lg border border-gray-200 px-2 py-1.5 text-sm capitalize focus:border-brand-400 focus:outline-none"
        >
          {TIERS.map((t) => (
            <option key={t} value={t}>
              {t}
            </option>
          ))}
        </select>
      </td>
      <td className="px-4 py-3 text-xs text-gray-400">
        {device.last_synced_at
          ? new Date(device.last_synced_at).toLocaleDateString()
          : "manual"}
      </td>
      <td className="px-4 py-3 text-right">
        {savedAt && !dirty ? (
          <span className="text-xs font-medium text-emerald-600">Saved</span>
        ) : (
          <button
            onClick={save}
            disabled={!dirty || saving || price === ""}
            className="rounded-lg bg-gray-900 px-3 py-1.5 text-xs font-semibold text-white transition hover:bg-gray-700 disabled:cursor-not-allowed disabled:bg-gray-200 disabled:text-gray-400"
          >
            Save
          </button>
        )}
      </td>
    </tr>
  );
}

export default function AdminPricingPage() {
  const [devices, setDevices] = useState<AdminDevice[]>([]);
  const [search, setSearch] = useState("");
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const load = useCallback(() => {
    setLoading(true);
    listDevices({ search: search || undefined })
      .then(setDevices)
      .catch((e) => setError(e.message))
      .finally(() => setLoading(false));
  }, [search]);

  useEffect(load, [load]);

  const missing = devices.filter((d) => !d.base_price).length;

  return (
    <main className="mx-auto max-w-6xl px-4 py-8 sm:px-6">
      <div className="flex flex-wrap items-end justify-between gap-4">
        <div>
          <h1 className="text-2xl font-bold tracking-tight text-gray-900">Pricing</h1>
          <p className="mt-1 text-sm text-gray-500">
            Base price is the competitor reference price. Manual edits are overwritten by the
            next price sync.
          </p>
        </div>
        <div className="relative">
          <SearchIcon className="pointer-events-none absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-gray-400" />
          <input
            placeholder="Search model…"
            value={search}
            onChange={(e) => setSearch(e.target.value)}
            className="w-56 rounded-xl border border-gray-200 bg-white py-2 pl-9 pr-3 text-sm shadow-soft focus:border-brand-400 focus:outline-none focus:ring-2 focus:ring-brand-100"
          />
        </div>
      </div>

      {missing > 0 && !loading && (
        <p className="mt-4 flex items-center gap-2 rounded-xl bg-amber-50 px-4 py-3 text-sm text-amber-800">
          <AlertTriangleIcon className="h-4 w-4 shrink-0" />
          {missing} device{missing === 1 ? "" : "s"} have no base price yet — they show as
          &ldquo;price coming soon&rdquo; to customers and can&apos;t be quoted.
        </p>
      )}

      {error && (
        <p className="mt-4 rounded-xl bg-red-50 px-4 py-3 text-sm text-red-700">{error}</p>
      )}

      <div className="mt-6 overflow-hidden rounded-2xl border border-gray-200 bg-white shadow-card">
        <div className="overflow-x-auto">
          <table className="w-full text-sm">
            <thead className="border-b border-gray-200 bg-gray-50 text-left text-xs uppercase tracking-wide text-gray-500">
              <tr>
                <th className="px-4 py-3 font-semibold">Device</th>
                <th className="px-4 py-3 font-semibold">Base price</th>
                <th className="px-4 py-3 font-semibold">Markup</th>
                <th className="px-4 py-3 font-semibold">Liquidity</th>
                <th className="px-4 py-3 font-semibold">Synced</th>
                <th className="px-4 py-3" />
              </tr>
            </thead>
            <tbody className="divide-y divide-gray-100">
              {loading && (
                <tr>
                  <td colSpan={6} className="px-4 py-10 text-center text-gray-400">
                    Loading…
                  </td>
                </tr>
              )}
              {devices.map((d) => (
                <PriceRow
                  key={d.id}
                  device={d}
                  onSaved={(updated) =>
                    setDevices((prev) => prev.map((x) => (x.id === updated.id ? updated : x)))
                  }
                />
              ))}
            </tbody>
          </table>
        </div>
      </div>
    </main>
  );
}

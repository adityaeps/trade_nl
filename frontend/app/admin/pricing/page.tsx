"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import {
  getPriceSyncStatus,
  listDevices,
  startPriceSync,
  updateBasePrice,
  SyncAlreadyRunningError,
  type AdminDevice,
  type PriceSyncStatus,
} from "@/lib/adminApi";
import { AlertTriangleIcon, RefreshIcon, SearchIcon } from "@/lib/icons";
import { useDebouncedValue } from "@/lib/useDebouncedValue";

const TIERS = ["high", "medium", "low"];

// How often to poll while a sync runs. Each device takes a couple of
// seconds to scrape, so anything faster just adds requests without
// showing the operator anything new.
const SYNC_POLL_MS = 3000;

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

/**
 * Manual competitor price sync.
 *
 * There is no scheduled run any more (see ARCHITECTURE.md §7 and
 * .github/workflows/sync-prices.yml) - the API isn't up around the clock,
 * so staff start the sync here and watch it finish. The backend runs it on
 * a background thread and this panel polls for progress; leaving the tab
 * open is also what keeps the API instance awake for the run.
 */
function PriceSyncPanel({ onFinished }: { onFinished: () => void }) {
  const [sync, setSync] = useState<PriceSyncStatus | null>(null);
  const [missingOnly, setMissingOnly] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [showFailures, setShowFailures] = useState(false);
  const wasRunning = useRef(false);

  const running = sync?.status === "running";

  const poll = useCallback(async () => {
    try {
      const next = await getPriceSyncStatus();
      setSync(next);
      // Refresh the table only on the running -> done edge, not on every
      // poll: re-fetching mid-run would blow away half-typed edits in the
      // rows below.
      if (wasRunning.current && next.status !== "running") onFinished();
      wasRunning.current = next.status === "running";
      return next;
    } catch (e: any) {
      setError(e.message);
      return null;
    }
  }, [onFinished]);

  useEffect(() => {
    // Picks up a run someone else started (or one still going after a
    // page reload) rather than showing an idle button next to it.
    poll();
  }, [poll]);

  useEffect(() => {
    if (!running) return;
    const id = setInterval(poll, SYNC_POLL_MS);
    return () => clearInterval(id);
  }, [running, poll]);

  async function run() {
    setError(null);
    setShowFailures(false);
    try {
      setSync(await startPriceSync(missingOnly));
      wasRunning.current = true;
    } catch (e: any) {
      if (e instanceof SyncAlreadyRunningError) {
        poll(); // someone beat us to it - just show their run
        return;
      }
      setError(e.message);
    }
  }

  const pct =
    sync && sync.total_devices > 0
      ? Math.round((sync.processed / sync.total_devices) * 100)
      : 0;

  return (
    <div className="mt-6 rounded-2xl border border-gray-200 bg-white p-4 shadow-card">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div>
          <h2 className="text-sm font-semibold text-gray-900">Competitor price sync</h2>
          <p className="mt-0.5 text-xs text-gray-500">
            Nothing runs on a schedule — start a run here when you want fresh competitor
            prices. Keep this tab open until it finishes.
          </p>
        </div>
        <div className="flex items-center gap-3">
          <label className="flex items-center gap-2 text-xs text-gray-600">
            <input
              type="checkbox"
              checked={missingOnly}
              disabled={running}
              onChange={(e) => setMissingOnly(e.target.checked)}
              className="h-3.5 w-3.5 rounded border-gray-300 text-brand-500 focus:ring-brand-200"
            />
            Only devices with no price
          </label>
          <button
            onClick={run}
            disabled={running}
            className="inline-flex items-center gap-2 rounded-lg bg-gray-900 px-3.5 py-2 text-xs font-semibold text-white transition hover:bg-gray-700 disabled:cursor-not-allowed disabled:bg-gray-200 disabled:text-gray-400"
          >
            <RefreshIcon className={`h-4 w-4 ${running ? "animate-spin" : ""}`} />
            {running ? "Syncing…" : "Run price sync"}
          </button>
        </div>
      </div>

      {error && <p className="mt-3 text-xs text-red-600">{error}</p>}

      {running && (
        <div className="mt-3">
          <div className="h-1.5 w-full overflow-hidden rounded-full bg-gray-100">
            <div
              className="h-full rounded-full bg-brand-500 transition-all duration-500"
              style={{ width: `${pct}%` }}
            />
          </div>
          <p className="mt-2 text-xs text-gray-500">
            {sync!.processed} of {sync!.total_devices || "…"} devices
            {sync!.current_device ? ` · ${sync!.current_device}` : ""}
          </p>
        </div>
      )}

      {sync && !running && sync.status !== "idle" && (
        <div className="mt-3 text-xs">
          <p className={sync.status === "failed" ? "text-red-600" : "text-gray-600"}>
            {sync.status === "failed"
              ? `Sync failed: ${sync.error ?? "unknown error"}`
              : `Last run ${
                  sync.finished_at ? new Date(sync.finished_at).toLocaleString() : ""
                } — ${sync.updated} updated, ${sync.failed} left unchanged.`}
          </p>
          {sync.failures.length > 0 && (
            <>
              <button
                onClick={() => setShowFailures((v) => !v)}
                className="mt-1 font-medium text-gray-500 underline hover:text-gray-700"
              >
                {showFailures ? "Hide" : "Show"} the {sync.failures.length} device
                {sync.failures.length === 1 ? "" : "s"} that couldn&apos;t be priced
              </button>
              {showFailures && (
                <ul className="mt-2 max-h-40 space-y-1 overflow-y-auto rounded-lg bg-gray-50 p-3 text-gray-500">
                  {sync.failures.map((f) => (
                    <li key={f}>{f}</li>
                  ))}
                </ul>
              )}
            </>
          )}
        </div>
      )}
    </div>
  );
}

export default function AdminPricingPage() {
  const [devices, setDevices] = useState<AdminDevice[]>([]);
  const [search, setSearch] = useState("");
  const debouncedSearch = useDebouncedValue(search);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  // Bumped when a sync finishes, and folded into each row's key so the rows
  // remount. A row's inputs seed from its props on mount only, so without
  // this a just-synced price keeps showing the old figure - and the row
  // reads as having unsaved edits it doesn't have. It has to be bumped in
  // the same update as the new rows, not before the fetch: remounting
  // against the data still on screen just re-seeds the stale figure.
  const [syncKey, setSyncKey] = useState(0);

  const load = useCallback(
    (remountRows = false) => {
      setLoading(true);
      listDevices({ search: debouncedSearch || undefined })
        .then((rows) => {
          setDevices(rows);
          if (remountRows) setSyncKey((k) => k + 1);
        })
        .catch((e) => setError(e.message))
        .finally(() => setLoading(false));
    },
    [debouncedSearch]
  );

  useEffect(() => {
    load();
  }, [load]);

  // Stable identity: PriceSyncPanel derives its polling callbacks from this,
  // and a fresh function every render would restart the poll effect in a
  // loop.
  const handleSyncFinished = useCallback(() => load(true), [load]);

  const missing = devices.filter((d) => !d.base_price).length;

  return (
    <main className="mx-auto max-w-6xl px-4 py-8 sm:px-6">
      <div className="flex flex-wrap items-end justify-between gap-4">
        <div>
          <h1 className="text-2xl font-bold tracking-tight text-gray-900">Pricing</h1>
          <p className="mt-1 text-sm text-gray-500">
            Base price is the competitor reference price. Manual edits are overwritten the
            next time you run the price sync.
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

      <PriceSyncPanel onFinished={handleSyncFinished} />

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
                  key={`${d.id}:${syncKey}`}
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

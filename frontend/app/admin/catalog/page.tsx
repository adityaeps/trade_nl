"use client";

import { useCallback, useEffect, useState } from "react";
import {
  deactivateDevice,
  listDevices,
  updateDevice,
  type AdminDevice,
} from "@/lib/adminApi";
import { SearchIcon } from "@/lib/icons";

const BRANDS = [
  { value: "", label: "All" },
  { value: "apple", label: "Apple" },
  { value: "samsung", label: "Samsung" },
];

export default function AdminCatalogPage() {
  const [devices, setDevices] = useState<AdminDevice[]>([]);
  const [brand, setBrand] = useState("");
  const [search, setSearch] = useState("");
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [savingId, setSavingId] = useState<string | null>(null);

  const load = useCallback(() => {
    setLoading(true);
    listDevices({ brand: brand || undefined, search: search || undefined })
      .then(setDevices)
      .catch((e) => setError(e.message))
      .finally(() => setLoading(false));
  }, [brand, search]);

  useEffect(load, [load]);

  async function patch(device: AdminDevice, changes: Partial<AdminDevice>) {
    setSavingId(device.id);
    setError(null);
    try {
      const updated = await updateDevice(device.id, changes);
      setDevices((prev) => prev.map((d) => (d.id === updated.id ? updated : d)));
    } catch (e: any) {
      setError(e.message);
    } finally {
      setSavingId(null);
    }
  }

  async function handleDeactivate(device: AdminDevice) {
    if (!confirm(`Deactivate ${device.model} ${device.storage_gb}GB? It will be hidden from the customer catalog. Existing quotes are unaffected.`)) return;
    setSavingId(device.id);
    try {
      await deactivateDevice(device.id);
      setDevices((prev) =>
        prev.map((d) => (d.id === device.id ? { ...d, is_active: false } : d))
      );
    } catch (e: any) {
      setError(e.message);
    } finally {
      setSavingId(null);
    }
  }

  return (
    <main className="mx-auto max-w-6xl px-4 py-8 sm:px-6">
      <div className="flex flex-wrap items-end justify-between gap-4">
        <div>
          <h1 className="text-2xl font-bold tracking-tight text-gray-900">Catalog</h1>
          <p className="mt-1 text-sm text-gray-500">
            {loading ? "Loading…" : `${devices.length} device${devices.length === 1 ? "" : "s"}`}
          </p>
        </div>
        <div className="flex flex-wrap items-center gap-3">
          <div className="flex gap-1 rounded-xl bg-gray-100 p-1">
            {BRANDS.map((b) => (
              <button
                key={b.value}
                onClick={() => setBrand(b.value)}
                className={`rounded-lg px-3 py-1.5 text-sm font-medium transition ${
                  brand === b.value ? "bg-white text-gray-900 shadow-soft" : "text-gray-500"
                }`}
              >
                {b.label}
              </button>
            ))}
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
      </div>

      {error && (
        <p className="mt-4 rounded-xl bg-red-50 px-4 py-3 text-sm text-red-700">{error}</p>
      )}

      <div className="mt-6 overflow-hidden rounded-2xl border border-gray-200 bg-white shadow-card">
        <div className="overflow-x-auto">
          <table className="w-full text-sm">
            <thead className="border-b border-gray-200 bg-gray-50 text-left text-xs uppercase tracking-wide text-gray-500">
              <tr>
                <th className="px-4 py-3 font-semibold">Device</th>
                <th className="px-4 py-3 font-semibold">Storage</th>
                <th className="px-4 py-3 font-semibold">Base price</th>
                <th className="px-4 py-3 font-semibold">S-Pen</th>
                <th className="px-4 py-3 font-semibold">Active</th>
                <th className="px-4 py-3" />
              </tr>
            </thead>
            <tbody className="divide-y divide-gray-100">
              {loading && (
                <tr>
                  <td colSpan={6} className="px-4 py-10 text-center text-gray-400">
                    Loading devices…
                  </td>
                </tr>
              )}
              {!loading && devices.length === 0 && (
                <tr>
                  <td colSpan={6} className="px-4 py-10 text-center text-gray-400">
                    No devices match.
                  </td>
                </tr>
              )}
              {devices.map((d) => (
                <tr
                  key={d.id}
                  className={`transition ${savingId === d.id ? "opacity-50" : ""} ${
                    d.is_active ? "" : "bg-gray-50/60"
                  }`}
                >
                  <td className="px-4 py-3">
                    <div className="flex items-center gap-3">
                      {d.image_url ? (
                        // eslint-disable-next-line @next/next/no-img-element
                        <img
                          src={d.image_url}
                          alt=""
                          className="h-9 w-9 shrink-0 rounded-lg object-contain"
                        />
                      ) : (
                        <span className="h-9 w-9 shrink-0 rounded-lg bg-gray-100" />
                      )}
                      <div>
                        <div className="font-medium text-gray-900">{d.model}</div>
                        <div className="text-xs text-gray-400">
                          {d.brand}
                          {d.color ? ` · ${d.color}` : ""}
                        </div>
                      </div>
                    </div>
                  </td>
                  <td className="px-4 py-3 tabular-nums text-gray-600">{d.storage_gb}GB</td>
                  <td className="px-4 py-3">
                    {d.base_price ? (
                      <span className="font-semibold tabular-nums text-emerald-700">
                        €{d.base_price}
                      </span>
                    ) : (
                      <span className="text-xs text-gray-400">not set</span>
                    )}
                  </td>
                  <td className="px-4 py-3">
                    <input
                      type="checkbox"
                      checked={d.has_s_pen}
                      disabled={savingId === d.id}
                      onChange={(e) => patch(d, { has_s_pen: e.target.checked })}
                      className="h-4 w-4 accent-brand-600"
                    />
                  </td>
                  <td className="px-4 py-3">
                    {d.is_active ? (
                      <span className="rounded-full bg-emerald-50 px-2 py-0.5 text-xs font-medium text-emerald-700">
                        Active
                      </span>
                    ) : (
                      <span className="rounded-full bg-gray-100 px-2 py-0.5 text-xs font-medium text-gray-500">
                        Hidden
                      </span>
                    )}
                  </td>
                  <td className="px-4 py-3 text-right">
                    {d.is_active ? (
                      <button
                        onClick={() => handleDeactivate(d)}
                        disabled={savingId === d.id}
                        className="text-xs font-medium text-gray-400 transition hover:text-red-600"
                      >
                        Deactivate
                      </button>
                    ) : (
                      <button
                        onClick={() => patch(d, { is_active: true })}
                        disabled={savingId === d.id}
                        className="text-xs font-medium text-brand-600 transition hover:text-brand-700"
                      >
                        Reactivate
                      </button>
                    )}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </div>
    </main>
  );
}

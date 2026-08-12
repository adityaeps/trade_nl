"use client";

import Link from "next/link";
import { useEffect, useState } from "react";
import { listDevices, type DeviceSummary } from "@/lib/api";
import { formatEur } from "@/lib/pricing";
import { AppleIcon, SamsungIcon, SearchIcon, SparkIcon } from "@/lib/icons";

const BRANDS = [
  { value: "", label: "All brands" },
  { value: "apple", label: "Apple" },
  { value: "samsung", label: "Samsung" },
];

function BrandBadge({
  brand,
  imageUrl,
  alt,
}: {
  brand: string;
  imageUrl?: string | null;
  alt?: string;
}) {
  const isApple = brand === "apple";
  // Falls back to the brand-logo tile if the device has no image_url, or if
  // the file 404s at runtime - so a missing/removed image degrades quietly
  // instead of showing a broken-image icon.
  const [failed, setFailed] = useState(false);

  if (imageUrl && !failed) {
    return (
      <div className="flex h-28 items-center justify-center rounded-xl bg-white">
        {/* eslint-disable-next-line @next/next/no-img-element */}
        <img
          src={imageUrl}
          alt={alt ?? ""}
          loading="lazy"
          onError={() => setFailed(true)}
          className="h-full w-full object-contain p-1"
        />
      </div>
    );
  }

  return (
    <div
      className={`flex h-28 items-center justify-center rounded-xl ${
        isApple
          ? "bg-gradient-to-br from-slate-100 to-slate-200 text-slate-500"
          : "bg-gradient-to-br from-blue-50 to-indigo-100 text-blue-500"
      }`}
    >
      {isApple ? <AppleIcon className="h-9 w-9" /> : <SamsungIcon className="h-9 w-9" />}
    </div>
  );
}

function CardSkeleton() {
  return (
    <div className="animate-pulse rounded-2xl border border-gray-200 bg-white p-4">
      <div className="h-28 rounded-xl bg-gray-100" />
      <div className="mt-4 h-4 w-2/3 rounded bg-gray-100" />
      <div className="mt-2 h-3 w-1/3 rounded bg-gray-100" />
      <div className="mt-4 h-5 w-1/2 rounded bg-gray-100" />
    </div>
  );
}

export default function CatalogPage() {
  const [devices, setDevices] = useState<DeviceSummary[]>([]);
  const [brand, setBrand] = useState("");
  const [search, setSearch] = useState("");
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    setLoading(true);
    setError(null);
    listDevices({ brand: brand || undefined, search: search || undefined })
      .then(setDevices)
      .catch((e) => setError(e.message))
      .finally(() => setLoading(false));
  }, [brand, search]);

  return (
    <main className="mx-auto max-w-5xl px-4 pb-20 pt-10 sm:px-6">
      <div className="animate-fade-in">
        <div className="inline-flex items-center gap-1.5 rounded-full border border-brand-200 bg-brand-50 px-3 py-1 text-xs font-semibold text-brand-700">
          <SparkIcon className="h-3.5 w-3.5" />
          Instant price, no strings attached
        </div>
        <h1 className="mt-4 text-4xl font-extrabold tracking-tight text-gray-900 sm:text-5xl">
          Sell your phone
          <span className="block bg-gradient-to-r from-brand-600 to-brand-400 bg-clip-text text-transparent">
            in minutes, not days.
          </span>
        </h1>
        <p className="mt-3 max-w-xl text-base text-gray-500">
          Pick your device, answer a few quick questions, and get a firm offer —
          then ship it or drop it off at a store near you.
        </p>
      </div>

      <div className="mt-8 flex flex-col gap-3 sm:flex-row sm:items-center">
        <div className="flex gap-2 rounded-xl bg-gray-100 p-1">
          {BRANDS.map((b) => (
            <button
              key={b.value}
              onClick={() => setBrand(b.value)}
              className={`rounded-lg px-4 py-1.5 text-sm font-medium transition-all ${
                brand === b.value
                  ? "bg-white text-gray-900 shadow-soft"
                  : "text-gray-500 hover:text-gray-700"
              }`}
            >
              {b.label}
            </button>
          ))}
        </div>
        <div className="relative sm:ml-auto sm:w-64">
          <SearchIcon className="pointer-events-none absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-gray-400" />
          <input
            type="text"
            placeholder="Search model…"
            value={search}
            onChange={(e) => setSearch(e.target.value)}
            className="w-full rounded-xl border border-gray-200 bg-white py-2 pl-9 pr-3 text-sm shadow-soft transition focus:border-brand-400 focus:outline-none focus:ring-2 focus:ring-brand-100"
          />
        </div>
      </div>

      {error && (
        <p className="mt-6 rounded-xl bg-red-50 px-4 py-3 text-sm text-red-700">
          Couldn&apos;t load devices: {error}
        </p>
      )}

      {!loading && !error && devices.length === 0 && (
        <p className="mt-10 text-center text-sm text-gray-500">No devices match your search.</p>
      )}

      <div className="mt-6 grid grid-cols-1 gap-4 sm:grid-cols-2 md:grid-cols-3">
        {loading
          ? Array.from({ length: 6 }).map((_, i) => <CardSkeleton key={i} />)
          : devices.map((d, i) => (
              <Link
                key={d.id}
                href={`/devices/${d.slug}`}
                style={{ animationDelay: `${i * 30}ms` }}
                className="group animate-slide-up rounded-2xl border border-gray-200 bg-white p-4 opacity-0 [animation-fill-mode:forwards] transition-all duration-200 hover:-translate-y-0.5 hover:border-brand-200 hover:shadow-raised"
              >
                <BrandBadge brand={d.brand} imageUrl={d.image_url} alt={d.model} />
                <h2 className="mt-4 font-semibold text-gray-900 transition-colors group-hover:text-brand-700">
                  {d.model}
                </h2>
                <p className="text-sm text-gray-500">
                  {d.storage_gb}GB{d.color ? ` · ${d.color}` : ""}
                </p>
                <div className="mt-3 flex items-center justify-between">
                  <p className="text-lg font-bold text-emerald-700">
                    {d.price_up_to ? formatEur(d.price_up_to) : "—"}
                  </p>
                  {d.price_up_to ? (
                    <span className="text-xs font-medium text-gray-400">up to</span>
                  ) : (
                    <span className="rounded-full bg-gray-100 px-2 py-0.5 text-[11px] font-medium text-gray-500">
                      Coming soon
                    </span>
                  )}
                </div>
              </Link>
            ))}
      </div>
    </main>
  );
}

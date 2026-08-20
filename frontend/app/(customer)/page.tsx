"use client";

import Link from "next/link";
import Image from "next/image";
import { motion, AnimatePresence } from "motion/react";
import { useCallback, useEffect, useId, useRef, useState } from "react";
import { DEVICE_PAGE_SIZE, listDevices, type DeviceSummary } from "@/lib/api";
import { formatEur } from "@/lib/pricing";
import {
  AppleIcon,
  CheckCircleIcon,
  SamsungIcon,
  SearchIcon,
  ShieldIcon,
  SparkIcon,
  TruckIcon,
  XCircleIcon,
} from "@/lib/icons";

// Honest, verifiable process facts - not review counts or testimonials we
// have no real data to back (this app has no accounts, no review system).
const TRUST_POINTS = [
  { icon: ShieldIcon, label: "Bank details encrypted, never shown to staff" },
  { icon: TruckIcon, label: "Ship for free or drop off in-store" },
  { icon: CheckCircleIcon, label: "No account, no obligation to accept" },
];

// Shared by the loading skeleton and every real card so a device with no
// price yet doesn't render shorter than one that has - see the ux skill's
// "Content Jumping" rule (reserve stable space for async/variable content).
const CARD_FOOTER_HEIGHT = "h-7";

const BRANDS = [
  { value: "", label: "All brands" },
  { value: "apple", label: "Apple" },
  { value: "samsung", label: "Samsung" },
];

function BrandBadge({
  brand,
  imageUrl,
  alt,
  priority,
}: {
  brand: string;
  imageUrl?: string | null;
  alt?: string;
  // First couple of rows are above the fold on first paint - fetching those
  // eagerly (not lazily) is what actually helps here, since lazy-loading an
  // image the browser needs immediately just delays it.
  priority?: boolean;
}) {
  const isApple = brand === "apple";
  // Falls back to the brand-logo tile if the device has no image_url, or if
  // the file 404s at runtime - so a missing/removed image degrades quietly
  // instead of showing a broken-image icon.
  const [failed, setFailed] = useState(false);

  if (imageUrl && !failed) {
    return (
      <div className="relative flex h-28 items-center justify-center rounded-xl bg-white p-1">
        {/* next/image resizes + serves WebP/AVIF instead of shipping the
            full 300x300 source PNG (~90KB) for a box that renders at ~110px -
            source files are all under frontend/public/, so no remote-pattern
            config is needed. */}
        <Image
          src={imageUrl}
          alt={alt ?? ""}
          fill
          sizes="(max-width: 640px) 40vw, (max-width: 768px) 30vw, 200px"
          loading={priority ? "eager" : "lazy"}
          priority={priority}
          onError={() => setFailed(true)}
          className="object-contain"
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
    <div className="rounded-2xl border border-gray-200 bg-white p-4">
      <div className="h-28 animate-pulse rounded-xl bg-gray-100" />
      <div className="mt-4 h-4 w-2/3 animate-pulse rounded bg-gray-100" />
      <div className="mt-2 h-3 w-1/3 animate-pulse rounded bg-gray-100" />
      <div className={`mt-3 ${CARD_FOOTER_HEIGHT} w-1/2 animate-pulse rounded bg-gray-100`} />
    </div>
  );
}

export default function CatalogPage() {
  const [devices, setDevices] = useState<DeviceSummary[]>([]);
  const [brand, setBrand] = useState("");
  const [search, setSearch] = useState("");
  const [loading, setLoading] = useState(true);
  const [loadingMore, setLoadingMore] = useState(false);
  const [exhausted, setExhausted] = useState(false);
  const [error, setError] = useState<string | null>(null);

  // Guards against the observer firing repeatedly while a fetch is already
  // in flight - it re-triggers on every scroll pixel otherwise, and state
  // updates land too late to prevent duplicate pages.
  const fetching = useRef(false);
  const sentinel = useRef<HTMLDivElement | null>(null);
  const searchId = useId();

  // First page, and a fresh one whenever the filters change.
  useEffect(() => {
    let cancelled = false;
    setLoading(true);
    setError(null);
    setExhausted(false);
    fetching.current = true;

    listDevices({ brand: brand || undefined, search: search || undefined })
      .then((page) => {
        if (cancelled) return; // a newer filter won the race
        setDevices(page);
        setExhausted(page.length < DEVICE_PAGE_SIZE);
      })
      .catch((e) => !cancelled && setError(e.message))
      .finally(() => {
        if (cancelled) return;
        setLoading(false);
        fetching.current = false;
      });

    return () => {
      cancelled = true;
    };
  }, [brand, search]);

  const loadMore = useCallback(() => {
    if (fetching.current || exhausted || loading || error) return;
    fetching.current = true;
    setLoadingMore(true);

    listDevices({
      brand: brand || undefined,
      search: search || undefined,
      offset: devices.length,
    })
      .then((page) => {
        setDevices((prev) => {
          // Belt and braces: if a page somehow overlaps (a device added
          // between requests shifts the offset window), drop the repeats
          // rather than rendering duplicate keys.
          const seen = new Set(prev.map((d) => d.id));
          return [...prev, ...page.filter((d) => !seen.has(d.id))];
        });
        setExhausted(page.length < DEVICE_PAGE_SIZE);
      })
      .catch((e) => setError(e.message))
      .finally(() => {
        setLoadingMore(false);
        fetching.current = false;
      });
  }, [brand, search, devices.length, exhausted, loading, error]);

  // Load the next page when the sentinel below the grid comes into view.
  // rootMargin starts the fetch ~600px early so the next rows are usually
  // there by the time the customer scrolls to them.
  useEffect(() => {
    const node = sentinel.current;
    if (!node || exhausted) return;
    const observer = new IntersectionObserver(
      (entries) => entries[0].isIntersecting && loadMore(),
      { rootMargin: "600px" }
    );
    observer.observe(node);
    return () => observer.disconnect();
  }, [loadMore, exhausted]);

  return (
    <main className="mx-auto max-w-5xl px-4 pb-20 pt-10 sm:px-6">
      <motion.div
        initial={{ opacity: 0, y: 10 }}
        animate={{ opacity: 1, y: 0 }}
        transition={{ duration: 0.35, ease: "easeOut" }}
      >
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
        <p className="mt-3 max-w-xl text-base leading-relaxed text-gray-500">
          Pick your device, answer a few quick questions, and get a firm offer —
          then ship it or drop it off at a store near you.
        </p>

        <ul className="mt-6 flex flex-wrap gap-x-6 gap-y-2">
          {TRUST_POINTS.map(({ icon: Icon, label }) => (
            <li key={label} className="flex items-center gap-1.5 text-sm text-gray-600">
              <Icon className="h-4 w-4 shrink-0 text-brand-600" />
              {label}
            </li>
          ))}
        </ul>
      </motion.div>

      <div className="mt-8 flex flex-col gap-3 sm:flex-row sm:items-center">
        <div role="group" aria-label="Filter by brand" className="flex gap-2 rounded-xl bg-gray-100 p-1">
          {BRANDS.map((b) => (
            <button
              key={b.value}
              type="button"
              onClick={() => setBrand(b.value)}
              aria-pressed={brand === b.value}
              className={`cursor-pointer rounded-lg px-4 py-3 text-sm font-medium transition-all duration-200 ${
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
          <label htmlFor={searchId} className="sr-only">
            Search by model name
          </label>
          <SearchIcon className="pointer-events-none absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-gray-400" />
          <input
            id={searchId}
            type="text"
            placeholder="Search model…"
            value={search}
            onChange={(e) => setSearch(e.target.value)}
            className="w-full rounded-xl border border-gray-200 bg-white py-2 pl-9 pr-9 text-sm shadow-soft transition focus:border-brand-400 focus:outline-none focus:ring-2 focus:ring-brand-100"
          />
          {search && (
            <button
              type="button"
              onClick={() => setSearch("")}
              aria-label="Clear search"
              className="absolute right-0 top-1/2 flex h-11 w-11 -translate-y-1/2 cursor-pointer items-center justify-center text-gray-400 transition-colors hover:text-gray-600"
            >
              <XCircleIcon className="h-4 w-4" />
            </button>
          )}
        </div>
      </div>

      {error && (
        <p role="alert" className="mt-6 rounded-xl bg-red-50 px-4 py-3 text-sm text-red-700">
          Couldn&apos;t load devices: {error}
        </p>
      )}

      {!loading && !error && devices.length === 0 && (
        <div className="mt-10 flex flex-col items-center gap-3 text-center">
          <span className="flex h-12 w-12 items-center justify-center rounded-full bg-gray-100 text-gray-400">
            <SearchIcon className="h-5 w-5" />
          </span>
          <p className="text-sm text-gray-500">No devices match your search.</p>
          {search && (
            <button
              type="button"
              onClick={() => setSearch("")}
              className="cursor-pointer rounded-lg px-4 py-3 text-sm font-medium text-brand-600 transition-colors hover:text-brand-700"
            >
              Clear search
            </button>
          )}
        </div>
      )}

      <div
        aria-busy={loading}
        className="mt-6 grid grid-cols-1 gap-4 sm:grid-cols-2 md:grid-cols-3"
      >
        {loading ? (
          Array.from({ length: 6 }).map((_, i) => <CardSkeleton key={i} />)
        ) : (
          <AnimatePresence initial={false}>
            {devices.map((d, i) => (
              <motion.div
                key={d.id}
                layout
                initial={{ opacity: 0, y: 8 }}
                animate={{ opacity: 1, y: 0 }}
                exit={{ opacity: 0 }}
                transition={{ duration: 0.25, delay: Math.min(i, 12) * 0.02 }}
              >
                <Link
                  href={`/devices/${d.slug}`}
                  className="group block h-full rounded-2xl border border-gray-200 bg-white p-4 transition-all duration-200 hover:-translate-y-0.5 hover:border-brand-200 hover:shadow-raised"
                >
                  <BrandBadge brand={d.brand} imageUrl={d.image_url} alt={d.model} priority={i < 6} />
                  <h2 className="mt-4 font-semibold text-gray-900 transition-colors group-hover:text-brand-700">
                    {d.model}
                  </h2>
                  <p className="text-sm text-gray-500">
                    {d.storage_gb}GB{d.color ? ` · ${d.color}` : ""}
                  </p>
                  <div className={`mt-3 flex items-center justify-between ${CARD_FOOTER_HEIGHT}`}>
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
              </motion.div>
            ))}
          </AnimatePresence>
        )}
        {loadingMore && Array.from({ length: 3 }).map((_, i) => <CardSkeleton key={`more-${i}`} />)}
      </div>

      {/* Scroll target: crossing into view (or within 600px of it) pulls the
          next page. Rendered only while there is more to fetch, so it can't
          keep firing at the end of the list. */}
      {!loading && !exhausted && <div ref={sentinel} aria-hidden className="h-px" />}

      {!loading && exhausted && devices.length > DEVICE_PAGE_SIZE && (
        <p className="mt-10 text-center text-sm text-gray-400">
          That&apos;s all {devices.length} models.
        </p>
      )}
    </main>
  );
}

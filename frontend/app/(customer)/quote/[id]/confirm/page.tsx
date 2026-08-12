"use client";

import Link from "next/link";
import { useParams } from "next/navigation";
import { useEffect, useState } from "react";
import { confirmQuote, getQuote, listStores, type Quote, type Store } from "@/lib/api";
import { formatEur } from "@/lib/pricing";
import { ArrowLeftIcon, CheckCircleIcon, MapPinIcon, SparkIcon, StoreIcon, TruckIcon } from "@/lib/icons";

export default function ConfirmPage() {
  const params = useParams<{ id: string }>();
  const [quote, setQuote] = useState<Quote | null>(null);
  const [stores, setStores] = useState<Store[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [submitting, setSubmitting] = useState(false);
  const [confirmed, setConfirmed] = useState<Quote | null>(null);

  const [fulfillment, setFulfillment] = useState<"store" | "courier">("courier");
  const [storeId, setStoreId] = useState<number | null>(null);
  const [name, setName] = useState("");
  const [email, setEmail] = useState("");
  const [phone, setPhone] = useState("");
  const [iban, setIban] = useState("");
  const [accountHolder, setAccountHolder] = useState("");

  useEffect(() => {
    getQuote(params.id).then(setQuote).catch((e) => setError(e.message));
    listStores().then(setStores).catch(() => {});
  }, [params.id]);

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    if (fulfillment === "store" && storeId === null) {
      setError("Please choose a store.");
      return;
    }
    setSubmitting(true);
    setError(null);
    try {
      const result = await confirmQuote(params.id, {
        fulfillment_method: fulfillment,
        store_id: fulfillment === "store" ? storeId ?? undefined : undefined,
        customer_name: name,
        customer_email: email,
        customer_phone: phone,
        iban,
        account_holder_name: accountHolder,
      });
      setConfirmed(result);
    } catch (e: any) {
      setError(e.message);
    } finally {
      setSubmitting(false);
    }
  }

  if (confirmed) {
    return (
      <main className="mx-auto max-w-xl px-4 py-16 text-center sm:px-6">
        <div className="animate-slide-up rounded-2xl border border-emerald-100 bg-white p-8 shadow-card">
          <div className="mx-auto flex h-14 w-14 items-center justify-center rounded-full bg-emerald-50 text-emerald-600">
            <SparkIcon className="h-7 w-7" />
          </div>
          <h1 className="mt-4 text-xl font-bold text-gray-900">You&apos;re all set</h1>
          <p className="mt-2 text-sm leading-relaxed text-gray-500">
            {confirmed.fulfillment_method === "store"
              ? "Drop your device off at the store you selected."
              : "We'll email you a shipping label to send your device in."}{" "}
            After inspection,{" "}
            <span className="font-semibold text-emerald-700">
              {formatEur(confirmed.calculated_price)}
            </span>{" "}
            will be transferred to the account you provided.
          </p>
          <p className="mt-4 text-xs text-gray-400">
            Reference:{" "}
            <span className="rounded bg-gray-100 px-1.5 py-0.5 font-mono text-gray-600">
              {confirmed.id}
            </span>
          </p>
        </div>
        <Link
          href="/"
          className="mt-6 inline-flex items-center gap-1.5 text-sm font-medium text-gray-500 transition hover:text-brand-600"
        >
          <ArrowLeftIcon className="h-4 w-4" /> Back to catalog
        </Link>
      </main>
    );
  }

  if (error && !quote)
    return (
      <main className="mx-auto max-w-xl px-4 py-16 sm:px-6">
        <p className="rounded-xl bg-red-50 px-4 py-3 text-center text-sm text-red-700">
          Couldn&apos;t load quote: {error}
        </p>
      </main>
    );
  if (!quote)
    return (
      <main className="mx-auto max-w-xl px-4 py-16 sm:px-6">
        <div className="animate-pulse h-48 rounded-2xl bg-gray-100" />
      </main>
    );

  if (quote.status !== "pending") {
    return (
      <main className="mx-auto max-w-xl px-4 py-16 text-center sm:px-6">
        <p className="text-gray-600">This quote can&apos;t be confirmed right now.</p>
        <Link
          href={`/quote/${quote.id}`}
          className="mt-4 inline-flex items-center gap-1.5 text-sm font-medium text-gray-500 transition hover:text-brand-600"
        >
          <ArrowLeftIcon className="h-4 w-4" /> Back to your quote
        </Link>
      </main>
    );
  }

  return (
    <main className="mx-auto max-w-xl px-4 pb-24 pt-8 sm:px-6">
      <Link
        href={`/quote/${quote.id}`}
        className="inline-flex items-center gap-1.5 text-sm font-medium text-gray-500 transition hover:text-brand-600"
      >
        <ArrowLeftIcon className="h-4 w-4" /> Back
      </Link>
      <h1 className="mt-4 text-2xl font-bold tracking-tight text-gray-900 sm:text-3xl">
        Complete your trade-in
      </h1>
      <p className="mt-1 text-sm text-gray-500">
        Offer:{" "}
        <span className="font-semibold text-emerald-700">
          {formatEur(quote.calculated_price)}
        </span>
      </p>

      <form onSubmit={handleSubmit} className="mt-8 space-y-7">
        <div>
          <p className="mb-2 text-sm font-medium text-gray-800">How will you send your device?</p>
          <div className="grid grid-cols-2 gap-3">
            {(
              [
                { key: "courier", label: "Ship it", desc: "Free shipping label by email", icon: TruckIcon },
                { key: "store", label: "Drop off in-store", desc: "Same-day, no waiting", icon: StoreIcon },
              ] as const
            ).map((opt) => {
              const Icon = opt.icon;
              const selected = fulfillment === opt.key;
              return (
                <button
                  key={opt.key}
                  type="button"
                  onClick={() => setFulfillment(opt.key)}
                  className={`flex flex-col items-start gap-2 rounded-xl border p-4 text-left transition-all ${
                    selected
                      ? "border-brand-500 bg-brand-50 shadow-soft"
                      : "border-gray-200 bg-white hover:border-brand-200"
                  }`}
                >
                  <Icon className={selected ? "h-5 w-5 text-brand-600" : "h-5 w-5 text-gray-400"} />
                  <span className="text-sm font-semibold text-gray-900">{opt.label}</span>
                  <span className="text-xs text-gray-500">{opt.desc}</span>
                </button>
              );
            })}
          </div>
        </div>

        {fulfillment === "store" && (
          <div className="animate-slide-up">
            <p className="mb-2 text-sm font-medium text-gray-800">Choose a store</p>
            <div className="space-y-2">
              {stores.map((s) => {
                const selected = storeId === s.id;
                return (
                  <label
                    key={s.id}
                    className={`flex cursor-pointer items-start gap-3 rounded-xl border p-3.5 text-sm transition-all ${
                      selected ? "border-brand-500 bg-brand-50" : "border-gray-200 hover:border-brand-200"
                    }`}
                  >
                    <input
                      type="radio"
                      name="store"
                      className="mt-1"
                      checked={selected}
                      onChange={() => setStoreId(s.id)}
                    />
                    <MapPinIcon
                      className={`mt-0.5 h-4 w-4 shrink-0 ${selected ? "text-brand-600" : "text-gray-400"}`}
                    />
                    <span>
                      <span className="block font-medium text-gray-900">{s.name}</span>
                      <span className="block text-gray-500">
                        {s.address_line}, {s.postal_code} {s.city}
                      </span>
                    </span>
                  </label>
                );
              })}
              {stores.length === 0 && (
                <p className="text-sm text-gray-500">No stores available yet.</p>
              )}
            </div>
          </div>
        )}

        <div className="grid grid-cols-1 gap-4 sm:grid-cols-2">
          <Field label="Full name" value={name} onChange={setName} required />
          <Field label="Email" type="email" value={email} onChange={setEmail} required />
          <Field label="Phone" value={phone} onChange={setPhone} required />
          <Field label="Account holder name" value={accountHolder} onChange={setAccountHolder} required />
        </div>
        <Field label="IBAN" value={iban} onChange={setIban} required placeholder="NL91 ABNA 0417 1643 00" />

        {error && (
          <p className="rounded-xl bg-red-50 px-4 py-3 text-sm text-red-700">{error}</p>
        )}

        <button
          type="submit"
          disabled={submitting}
          className="flex w-full items-center justify-center gap-2 rounded-xl bg-gradient-to-r from-brand-600 to-brand-500 px-4 py-3.5 font-semibold text-white shadow-raised transition-all hover:brightness-105 active:scale-[0.99] disabled:cursor-not-allowed disabled:from-gray-300 disabled:to-gray-300 disabled:shadow-none"
        >
          {submitting ? (
            "Confirming…"
          ) : (
            <>
              <CheckCircleIcon className="h-[18px] w-[18px]" /> Confirm trade-in
            </>
          )}
        </button>
      </form>
    </main>
  );
}

function Field({
  label,
  value,
  onChange,
  type = "text",
  required,
  placeholder,
}: {
  label: string;
  value: string;
  onChange: (v: string) => void;
  type?: string;
  required?: boolean;
  placeholder?: string;
}) {
  return (
    <label className="block text-sm">
      <span className="mb-1.5 block font-medium text-gray-800">{label}</span>
      <input
        type={type}
        value={value}
        required={required}
        placeholder={placeholder}
        onChange={(e) => onChange(e.target.value)}
        className="w-full rounded-xl border border-gray-200 bg-white px-3.5 py-2.5 shadow-soft transition focus:border-brand-400 focus:outline-none focus:ring-2 focus:ring-brand-100"
      />
    </label>
  );
}

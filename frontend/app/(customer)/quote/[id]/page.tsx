"use client";

import Link from "next/link";
import { useParams } from "next/navigation";
import { useEffect, useState } from "react";
import { getQuote, type Quote } from "@/lib/api";
import { formatEur } from "@/lib/pricing";
import { AlertTriangleIcon, ArrowLeftIcon, SparkIcon, XCircleIcon } from "@/lib/icons";

function AnswersSummary({ quote }: { quote: Quote }) {
  if (quote.answers_detail.length === 0) return null;
  return (
    <div className="animate-slide-up mt-6 rounded-2xl border border-gray-200 bg-white p-5 text-left shadow-card">
      <h2 className="text-sm font-semibold text-gray-900">Your answers</h2>
      <dl className="mt-3 divide-y divide-gray-100">
        {quote.answers_detail.map((a) => (
          <div key={a.question_id} className="flex items-start justify-between gap-4 py-2.5">
            <dt className="text-sm text-gray-500">{a.question_text}</dt>
            <dd className="shrink-0 rounded-full bg-gray-100 px-2.5 py-0.5 text-right text-xs font-medium text-gray-700">
              {a.selected_label}
            </dd>
          </div>
        ))}
      </dl>
    </div>
  );
}

export default function QuoteResultPage() {
  const params = useParams<{ id: string }>();
  const [quote, setQuote] = useState<Quote | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    getQuote(params.id).then(setQuote).catch((e) => setError(e.message));
  }, [params.id]);

  if (error)
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
        <div className="animate-pulse space-y-4">
          <div className="mx-auto h-40 w-full rounded-2xl bg-gray-100" />
        </div>
      </main>
    );

  if (quote.status === "rejected") {
    return (
      <main className="mx-auto max-w-xl px-4 py-16 text-center sm:px-6">
        <div className="animate-slide-up rounded-2xl border border-red-100 bg-white p-8 shadow-card">
          <div className="mx-auto flex h-14 w-14 items-center justify-center rounded-full bg-red-50 text-red-500">
            <XCircleIcon className="h-7 w-7" />
          </div>
          <h1 className="mt-4 text-xl font-bold text-gray-900">We can&apos;t buy this device</h1>
          <p className="mt-2 text-sm leading-relaxed text-gray-500">
            Based on your answers, this device doesn&apos;t qualify for a trade-in offer (for
            example, SIM-locked devices can&apos;t be accepted). No further action is needed.
          </p>
        </div>
        <AnswersSummary quote={quote} />
        <Link
          href="/"
          className="mt-6 inline-flex items-center gap-1.5 text-sm font-medium text-gray-500 transition hover:text-brand-600"
        >
          <ArrowLeftIcon className="h-4 w-4" /> Back to catalog
        </Link>
      </main>
    );
  }

  if (quote.status === "manual_review") {
    return (
      <main className="mx-auto max-w-xl px-4 py-16 text-center sm:px-6">
        <div className="animate-slide-up rounded-2xl border border-amber-100 bg-white p-8 shadow-card">
          <div className="mx-auto flex h-14 w-14 items-center justify-center rounded-full bg-amber-50 text-amber-600">
            <AlertTriangleIcon className="h-7 w-7" />
          </div>
          <h1 className="mt-4 text-xl font-bold text-gray-900">We need to take a closer look</h1>
          <p className="mt-2 text-sm leading-relaxed text-gray-500">
            Based on your answers (for example water damage, a broken screen or housing, or the
            device not powering on), we can&apos;t give an automatic price. Our team will review
            it in more detail — please check back or contact support with reference{" "}
            <span className="rounded bg-gray-100 px-1.5 py-0.5 font-mono text-xs text-gray-700">
              {quote.id}
            </span>
            .
          </p>
        </div>
        <AnswersSummary quote={quote} />
        <Link
          href="/"
          className="mt-6 inline-flex items-center gap-1.5 text-sm font-medium text-gray-500 transition hover:text-brand-600"
        >
          <ArrowLeftIcon className="h-4 w-4" /> Back to catalog
        </Link>
      </main>
    );
  }

  return (
    <main className="mx-auto max-w-xl px-4 py-16 text-center sm:px-6">
      <div className="animate-slide-up rounded-2xl border border-emerald-100 bg-white p-8 shadow-card">
        <div className="mx-auto flex h-14 w-14 items-center justify-center rounded-full bg-emerald-50 text-emerald-600">
          <SparkIcon className="h-7 w-7" />
        </div>
        <h1 className="mt-4 text-xs font-semibold uppercase tracking-wide text-emerald-600">
          Your offer
        </h1>
        <p className="mt-1 text-5xl font-extrabold tracking-tight text-gray-900">
          {formatEur(quote.calculated_price)}
        </p>
        <p className="mt-3 text-sm text-gray-500">
          Valid until{" "}
          <span className="font-medium text-gray-700">
            {new Date(quote.valid_until).toLocaleDateString()}
          </span>
        </p>
      </div>
      <AnswersSummary quote={quote} />
      <Link
        href={`/quote/${quote.id}/confirm`}
        className="mt-6 block w-full rounded-xl bg-gradient-to-r from-brand-600 to-brand-500 px-4 py-3.5 font-semibold text-white shadow-raised transition-all hover:brightness-105 active:scale-[0.99]"
      >
        Continue
      </Link>
    </main>
  );
}

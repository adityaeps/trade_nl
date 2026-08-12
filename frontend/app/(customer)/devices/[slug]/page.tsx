"use client";

import Link from "next/link";
import { useParams, useRouter } from "next/navigation";
import { useEffect, useMemo, useState } from "react";
import { createQuote, getDevice, type DeviceDetail, type Question } from "@/lib/api";
import { estimatePrice, filterActiveQuestions, findDisqualification, formatEur } from "@/lib/pricing";
import { AlertTriangleIcon, ArrowLeftIcon, CheckCircleIcon, XCircleIcon } from "@/lib/icons";

function QuestionInput({
  question,
  value,
  onChange,
}: {
  question: Question;
  value: string | undefined;
  onChange: (value: string) => void;
}) {
  const isBoolean = question.type === "boolean";
  return (
    <div className={isBoolean ? "flex gap-2" : "flex flex-wrap gap-2"}>
      {question.options.map((opt) => {
        const selected = value === opt.value;
        return (
          <button
            key={opt.value}
            onClick={() => onChange(opt.value)}
            className={`group relative flex items-center gap-2 rounded-xl border px-4 py-2.5 text-sm font-medium transition-all ${
              isBoolean ? "flex-1 justify-center sm:flex-none sm:justify-start" : ""
            } ${
              selected
                ? "border-brand-500 bg-brand-500 text-white shadow-soft"
                : "border-gray-200 bg-white text-gray-700 hover:border-brand-300 hover:bg-brand-50/50"
            }`}
          >
            {selected && <CheckCircleIcon className="h-4 w-4" />}
            {opt.label}
          </button>
        );
      })}
    </div>
  );
}

function ProgressBar({ done, total }: { done: number; total: number }) {
  const pct = total === 0 ? 0 : Math.round((done / total) * 100);
  return (
    <div className="flex items-center gap-3">
      <div className="h-1.5 flex-1 overflow-hidden rounded-full bg-gray-100">
        <div
          className="h-full rounded-full bg-gradient-to-r from-brand-400 to-brand-600 transition-all duration-300"
          style={{ width: `${pct}%` }}
        />
      </div>
      <span className="whitespace-nowrap text-xs font-medium text-gray-400">
        {done}/{total} answered
      </span>
    </div>
  );
}

export default function DeviceDetailPage() {
  const params = useParams<{ slug: string }>();
  const router = useRouter();
  const [device, setDevice] = useState<DeviceDetail | null>(null);
  const [answers, setAnswers] = useState<Record<string, string>>({});
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [submitting, setSubmitting] = useState(false);

  useEffect(() => {
    setLoading(true);
    setAnswers({});
    getDevice(params.slug)
      .then(setDevice)
      .catch((e) => setError(e.message))
      .finally(() => setLoading(false));
  }, [params.slug]);

  const dealQuestions = useMemo(
    () => (device ? device.questions.filter((q) => q.type !== "device_selector") : []),
    [device]
  );
  const activeQuestions = useMemo(
    () => filterActiveQuestions(dealQuestions, answers),
    [dealQuestions, answers]
  );
  const deviceSelectorQuestion = device?.questions.find((q) => q.type === "device_selector");

  const disqualification = findDisqualification(activeQuestions, answers);
  const basePrice = device?.price_up_to ? Number(device.price_up_to) : 0;
  const liveEstimate = estimatePrice(basePrice, activeQuestions, answers);
  const answeredCount = activeQuestions.filter((q) => answers[String(q.id)] !== undefined).length;
  const allAnswered = activeQuestions.length > 0 && answeredCount === activeQuestions.length;

  async function handleSubmit() {
    if (!device) return;
    setSubmitting(true);
    setError(null);
    try {
      const quote = await createQuote(device.id, answers);
      router.push(`/quote/${quote.id}`);
    } catch (e: any) {
      setError(e.message);
      setSubmitting(false);
    }
  }

  if (loading) {
    return (
      <main className="mx-auto max-w-3xl px-4 py-10 sm:px-6">
        <div className="animate-pulse space-y-6">
          <div className="h-4 w-24 rounded bg-gray-100" />
          <div className="h-8 w-64 rounded bg-gray-100" />
          <div className="h-28 rounded-2xl bg-gray-100" />
          <div className="h-16 rounded-2xl bg-gray-100" />
          <div className="h-16 rounded-2xl bg-gray-100" />
        </div>
      </main>
    );
  }
  if (error && !device)
    return (
      <main className="mx-auto max-w-3xl px-4 py-10 sm:px-6">
        <p className="rounded-xl bg-red-50 px-4 py-3 text-sm text-red-700">
          Couldn&apos;t load device: {error}
        </p>
      </main>
    );
  if (!device) return null;

  return (
    <main className="mx-auto max-w-3xl px-4 pb-24 pt-8 sm:px-6">
      <Link
        href="/"
        className="inline-flex items-center gap-1.5 text-sm font-medium text-gray-500 transition hover:text-brand-600"
      >
        <ArrowLeftIcon className="h-4 w-4" /> Back to catalog
      </Link>

      <div className="mt-4 flex items-start justify-between gap-4">
        <div className="flex items-center gap-4">
          {device.image_url && (
            // eslint-disable-next-line @next/next/no-img-element
            <img
              src={device.image_url}
              alt={device.model}
              className="h-20 w-20 shrink-0 rounded-xl bg-white object-contain p-1 shadow-soft"
              onError={(e) => {
                e.currentTarget.style.display = "none";
              }}
            />
          )}
          <div>
            <h1 className="text-2xl font-bold tracking-tight text-gray-900 sm:text-3xl">
              {device.model}
            </h1>
            <p className="text-sm text-gray-500">
              {device.storage_gb}GB{device.color ? ` · ${device.color}` : ""}
            </p>
          </div>
        </div>
        {device.price_up_to && (
          <div className="text-right">
            <p className="text-xs font-medium text-gray-400">Up to</p>
            <p className="whitespace-nowrap text-xl font-bold text-emerald-700">
              {formatEur(device.price_up_to)}
            </p>
          </div>
        )}
      </div>

      {!device.price_up_to && (
        <p className="mt-4 flex items-center gap-2 rounded-xl bg-amber-50 px-4 py-3 text-sm text-amber-800">
          <AlertTriangleIcon className="h-4 w-4 shrink-0" />
          We don&apos;t have a price for this device yet — check back soon.
        </p>
      )}

      {deviceSelectorQuestion && device.storage_variants.length > 1 && (
        <div className="mt-6">
          <p className="text-sm font-medium text-gray-700">{deviceSelectorQuestion.text}</p>
          <div className="mt-2 flex gap-2">
            {device.storage_variants.map((variant) => (
              <Link
                key={variant.id}
                href={`/devices/${variant.slug}`}
                className={`rounded-xl border px-4 py-2 text-sm font-medium transition-all ${
                  variant.slug === device.slug
                    ? "border-brand-500 bg-brand-500 text-white shadow-soft"
                    : "border-gray-200 bg-white text-gray-700 hover:border-brand-300"
                }`}
              >
                {variant.storage_gb}GB
              </Link>
            ))}
          </div>
        </div>
      )}

      {device.price_up_to && (
        <>
          <div className="sticky top-[57px] z-10 mt-8 -mx-4 rounded-2xl border border-gray-200 bg-white/90 p-5 shadow-card backdrop-blur-md sm:mx-0">
            <div className="flex items-baseline justify-between">
              <h2 className="font-semibold text-gray-900">Your estimate</h2>
              <p
                key={liveEstimate}
                className="animate-fade-in text-3xl font-extrabold tabular-nums text-emerald-700"
              >
                {formatEur(liveEstimate)}
              </p>
            </div>
            <div className="mt-3">
              <ProgressBar done={answeredCount} total={activeQuestions.length} />
            </div>
            {disqualification === "rejected" && (
              <p className="mt-3 flex items-center gap-2 rounded-lg bg-red-50 px-3 py-2 text-sm text-red-700">
                <XCircleIcon className="h-4 w-4 shrink-0" />
                Based on your answers, we won&apos;t be able to buy this device.
              </p>
            )}
            {disqualification === "manual_review" && (
              <p className="mt-3 flex items-center gap-2 rounded-lg bg-amber-50 px-3 py-2 text-sm text-amber-800">
                <AlertTriangleIcon className="h-4 w-4 shrink-0" />
                This device will need manual review before a final price.
              </p>
            )}
          </div>

          <div className="mt-6 space-y-5">
            {activeQuestions.map((q) => {
              const isBranch = Boolean(q.depends_on_question_id);
              const answered = answers[String(q.id)] !== undefined;
              return (
                <div
                  key={q.id}
                  className={`animate-slide-up rounded-2xl border p-4 transition-colors sm:p-5 ${
                    isBranch ? "ml-4 border-gray-100 bg-gray-50/60 sm:ml-8" : "border-gray-200 bg-white"
                  } ${answered ? "border-l-4 border-l-emerald-400" : ""}`}
                >
                  <p className="mb-3 text-sm font-medium text-gray-800">{q.text}</p>
                  <QuestionInput
                    question={q}
                    value={answers[String(q.id)]}
                    onChange={(value) => setAnswers((prev) => ({ ...prev, [String(q.id)]: value }))}
                  />
                </div>
              );
            })}
          </div>

          {error && (
            <p className="mt-4 rounded-xl bg-red-50 px-4 py-3 text-sm text-red-700">{error}</p>
          )}

          <button
            onClick={handleSubmit}
            disabled={!allAnswered || submitting}
            className="mt-8 w-full rounded-xl bg-gradient-to-r from-brand-600 to-brand-500 px-4 py-3.5 font-semibold text-white shadow-raised transition-all hover:brightness-105 active:scale-[0.99] disabled:cursor-not-allowed disabled:from-gray-300 disabled:to-gray-300 disabled:shadow-none"
          >
            {submitting ? "Getting your quote…" : "Get my quote"}
          </button>
        </>
      )}
    </main>
  );
}

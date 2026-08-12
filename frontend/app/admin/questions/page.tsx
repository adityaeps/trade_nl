"use client";

import { useCallback, useEffect, useState } from "react";
import {
  listQuestionSets,
  listQuestions,
  updateDeductionRule,
  updateQuestion,
  type AdminDeductionRule,
  type AdminQuestion,
  type AdminQuestionSet,
} from "@/lib/adminApi";
import { AlertTriangleIcon, XCircleIcon } from "@/lib/icons";

function RuleEditor({
  rule,
  question,
  onSaved,
}: {
  rule: AdminDeductionRule;
  question: AdminQuestion;
  onSaved: (r: AdminDeductionRule) => void;
}) {
  const [value, setValue] = useState(rule.deduction_value);
  const [type, setType] = useState(rule.deduction_type);
  const [disq, setDisq] = useState(rule.is_disqualifying);
  const [status, setStatus] = useState(rule.disqualify_status ?? "manual_review");
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const dirty =
    value !== rule.deduction_value ||
    type !== rule.deduction_type ||
    disq !== rule.is_disqualifying ||
    (disq && status !== rule.disqualify_status);

  const label =
    question.options.find((o) => o.value === rule.option_value)?.label ?? rule.option_value;

  async function save() {
    setSaving(true);
    setError(null);
    try {
      const updated = await updateDeductionRule(rule.id, {
        option_value: rule.option_value,
        deduction_type: type,
        deduction_value: disq ? "0" : value,
        is_disqualifying: disq,
        disqualify_status: disq ? (status as "rejected" | "manual_review") : null,
      });
      onSaved(updated);
    } catch (e: any) {
      setError(e.message);
    } finally {
      setSaving(false);
    }
  }

  return (
    <div
      className={`rounded-xl border p-3 transition ${
        disq
          ? status === "rejected"
            ? "border-red-200 bg-red-50/50"
            : "border-amber-200 bg-amber-50/50"
          : "border-gray-200 bg-white"
      } ${saving ? "opacity-50" : ""}`}
    >
      <div className="flex flex-wrap items-center gap-x-3 gap-y-2">
        <span className="min-w-0 flex-1 truncate text-sm font-medium text-gray-800">{label}</span>

        {!disq && (
          <div className="flex items-center gap-1">
            <span className="text-xs text-gray-400">−</span>
            <input
              value={value}
              onChange={(e) => setValue(e.target.value)}
              inputMode="decimal"
              className="w-20 rounded-lg border border-gray-200 px-2 py-1 text-sm tabular-nums focus:border-brand-400 focus:outline-none"
            />
            <select
              value={type}
              onChange={(e) => setType(e.target.value as "fixed" | "percentage")}
              className="rounded-lg border border-gray-200 px-2 py-1 text-sm focus:border-brand-400 focus:outline-none"
            >
              <option value="fixed">€</option>
              <option value="percentage">%</option>
            </select>
          </div>
        )}

        <label className="flex items-center gap-1.5 text-xs font-medium text-gray-600">
          <input
            type="checkbox"
            checked={disq}
            onChange={(e) => setDisq(e.target.checked)}
            className="h-3.5 w-3.5 accent-brand-600"
          />
          Disqualifying
        </label>

        {disq && (
          <select
            value={status}
            onChange={(e) => setStatus(e.target.value as "rejected" | "manual_review")}
            className="rounded-lg border border-gray-200 px-2 py-1 text-sm focus:border-brand-400 focus:outline-none"
          >
            <option value="manual_review">→ manual review</option>
            <option value="rejected">→ rejected</option>
          </select>
        )}

        <button
          onClick={save}
          disabled={!dirty || saving}
          className="ml-auto rounded-lg bg-gray-900 px-3 py-1 text-xs font-semibold text-white transition hover:bg-gray-700 disabled:cursor-not-allowed disabled:bg-gray-200 disabled:text-gray-400"
        >
          Save
        </button>
      </div>

      {disq && (
        <p className="mt-2 flex items-start gap-1.5 text-xs text-gray-500">
          {status === "rejected" ? (
            <XCircleIcon className="mt-px h-3.5 w-3.5 shrink-0 text-red-500" />
          ) : (
            <AlertTriangleIcon className="mt-px h-3.5 w-3.5 shrink-0 text-amber-500" />
          )}
          Skips price calculation entirely; the deduction amount is ignored.
        </p>
      )}
      {error && <p className="mt-2 text-xs text-red-600">{error}</p>}
    </div>
  );
}

function QuestionCard({
  question,
  allQuestions,
  onQuestionSaved,
  onRuleSaved,
}: {
  question: AdminQuestion;
  allQuestions: AdminQuestion[];
  onQuestionSaved: (q: AdminQuestion) => void;
  onRuleSaved: (r: AdminDeductionRule) => void;
}) {
  const [parentId, setParentId] = useState(question.depends_on_question_id ?? "");
  const [parentValue, setParentValue] = useState(question.depends_on_value ?? "");
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const parent = allQuestions.find((q) => q.id === Number(parentId));
  const dirty =
    (parentId === "" ? null : Number(parentId)) !== question.depends_on_question_id ||
    (parentValue === "" ? null : parentValue) !== question.depends_on_value;

  async function saveDependency() {
    setSaving(true);
    setError(null);
    try {
      const updated = await updateQuestion(question.id, {
        depends_on_question_id: parentId === "" ? null : Number(parentId),
        depends_on_value: parentId === "" ? null : parentValue,
      });
      onQuestionSaved(updated);
    } catch (e: any) {
      setError(e.message);
    } finally {
      setSaving(false);
    }
  }

  const candidates = allQuestions.filter(
    (q) => q.id !== question.id && q.question_set_id === question.question_set_id && q.options.length
  );

  return (
    <div
      className={`rounded-2xl border border-gray-200 bg-white p-5 shadow-card ${
        question.depends_on_question_id ? "ml-0 border-l-4 border-l-brand-300 sm:ml-6" : ""
      }`}
    >
      <div className="flex items-start justify-between gap-3">
        <div className="min-w-0">
          <div className="flex flex-wrap items-center gap-2">
            <span className="rounded-md bg-gray-100 px-1.5 py-0.5 text-xs font-medium tabular-nums text-gray-500">
              #{question.display_order}
            </span>
            <span className="rounded-md bg-gray-100 px-1.5 py-0.5 text-xs text-gray-500">
              {question.type}
            </span>
            {question.requires_device_attribute && (
              <span className="rounded-md bg-indigo-50 px-1.5 py-0.5 text-xs font-medium text-indigo-600">
                only if {question.requires_device_attribute}
              </span>
            )}
          </div>
          <h3 className="mt-2 font-semibold text-gray-900">{question.text}</h3>
        </div>
      </div>

      {/* Branching config */}
      <div className="mt-4 rounded-xl bg-gray-50 p-3">
        <p className="text-xs font-semibold uppercase tracking-wide text-gray-500">
          Show this question only when…
        </p>
        <div className="mt-2 flex flex-wrap items-center gap-2">
          <select
            value={parentId}
            onChange={(e) => {
              setParentId(e.target.value);
              setParentValue("");
            }}
            className="max-w-[18rem] rounded-lg border border-gray-200 bg-white px-2 py-1.5 text-sm focus:border-brand-400 focus:outline-none"
          >
            <option value="">Always show</option>
            {candidates.map((q) => (
              <option key={q.id} value={q.id}>
                #{q.display_order} {q.text.slice(0, 45)}
                {q.text.length > 45 ? "…" : ""}
              </option>
            ))}
          </select>

          {parentId !== "" && (
            <>
              <span className="text-sm text-gray-400">is</span>
              <select
                value={parentValue}
                onChange={(e) => setParentValue(e.target.value)}
                className="rounded-lg border border-gray-200 bg-white px-2 py-1.5 text-sm focus:border-brand-400 focus:outline-none"
              >
                <option value="">choose…</option>
                {parent?.options.map((o) => (
                  <option key={o.value} value={o.value}>
                    {o.label}
                  </option>
                ))}
              </select>
            </>
          )}

          <button
            onClick={saveDependency}
            disabled={!dirty || saving || (parentId !== "" && parentValue === "")}
            className="ml-auto rounded-lg bg-gray-900 px-3 py-1.5 text-xs font-semibold text-white transition hover:bg-gray-700 disabled:cursor-not-allowed disabled:bg-gray-200 disabled:text-gray-400"
          >
            Save
          </button>
        </div>
        {error && <p className="mt-2 text-xs text-red-600">{error}</p>}
      </div>

      {question.deduction_rules.length > 0 && (
        <div className="mt-4 space-y-2">
          <p className="text-xs font-semibold uppercase tracking-wide text-gray-500">
            Answers &amp; deductions
          </p>
          {question.deduction_rules.map((r) => (
            <RuleEditor key={r.id} rule={r} question={question} onSaved={onRuleSaved} />
          ))}
        </div>
      )}
    </div>
  );
}

export default function AdminQuestionsPage() {
  const [sets, setSets] = useState<AdminQuestionSet[]>([]);
  const [activeSet, setActiveSet] = useState<number | null>(null);
  const [questions, setQuestions] = useState<AdminQuestion[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    listQuestionSets()
      .then((s) => {
        setSets(s);
        if (s.length) setActiveSet(s[0].id);
      })
      .catch((e) => setError(e.message));
  }, []);

  const load = useCallback(() => {
    if (activeSet === null) return;
    setLoading(true);
    listQuestions(activeSet)
      .then(setQuestions)
      .catch((e) => setError(e.message))
      .finally(() => setLoading(false));
  }, [activeSet]);

  useEffect(load, [load]);

  return (
    <main className="mx-auto max-w-4xl px-4 py-8 sm:px-6">
      <h1 className="text-2xl font-bold tracking-tight text-gray-900">Questions</h1>
      <p className="mt-1 text-sm text-gray-500">
        Configure branching and per-answer deductions. Disqualifying answers skip pricing and set
        the quote status instead.
      </p>

      <div className="mt-6 flex flex-wrap gap-2">
        {sets.map((s) => (
          <button
            key={s.id}
            onClick={() => setActiveSet(s.id)}
            className={`rounded-xl border px-4 py-2 text-sm font-medium transition ${
              activeSet === s.id
                ? "border-brand-500 bg-brand-500 text-white shadow-soft"
                : "border-gray-200 bg-white text-gray-700 hover:border-brand-300"
            }`}
          >
            {s.name}
            <span className="ml-2 text-xs opacity-70">{s.question_count}</span>
          </button>
        ))}
      </div>

      {error && (
        <p className="mt-4 rounded-xl bg-red-50 px-4 py-3 text-sm text-red-700">{error}</p>
      )}

      <div className="mt-6 space-y-4">
        {loading && <p className="text-sm text-gray-400">Loading questions…</p>}
        {questions.map((q) => (
          <QuestionCard
            key={q.id}
            question={q}
            allQuestions={questions}
            onQuestionSaved={(updated) =>
              setQuestions((prev) => prev.map((x) => (x.id === updated.id ? updated : x)))
            }
            onRuleSaved={(rule) =>
              setQuestions((prev) =>
                prev.map((x) =>
                  x.id === rule.question_id
                    ? {
                        ...x,
                        deduction_rules: x.deduction_rules.map((r) =>
                          r.id === rule.id ? rule : r
                        ),
                      }
                    : x
                )
              )
            }
          />
        ))}
      </div>
    </main>
  );
}

import type { Question } from "./api";

/**
 * Client-side mirror of backend/app/services/pricing_engine.py, used only
 * to show a live running estimate while the customer answers questions.
 * The authoritative, frozen price always comes from POST /quotes - this
 * never gets persisted or trusted as the real price. See ARCHITECTURE.md §2
 * ("quotes are frozen once created") and app/schemas/device.py's note on
 * why deduction_rules are exposed via GET /devices/{slug} at all.
 */

export function filterActiveQuestions(
  questions: Question[],
  answers: Record<string, string>
): Question[] {
  return questions.filter((q) => {
    if (q.depends_on_question_id === null) return true;
    return answers[String(q.depends_on_question_id)] === q.depends_on_value;
  });
}

export function findDisqualification(
  questions: Question[],
  answers: Record<string, string>
): "rejected" | "manual_review" | null {
  const statuses = new Set<string>();
  for (const q of questions) {
    const answer = answers[String(q.id)];
    if (answer === undefined) continue;
    for (const rule of q.deduction_rules) {
      if (rule.is_disqualifying && rule.option_value === answer && rule.disqualify_status) {
        statuses.add(rule.disqualify_status);
      }
    }
  }
  if (statuses.has("rejected")) return "rejected";
  if (statuses.has("manual_review")) return "manual_review";
  return null;
}

export function estimatePrice(
  basePrice: number,
  questions: Question[],
  answers: Record<string, string>
): number {
  let price = basePrice;
  for (const q of questions) {
    const answer = answers[String(q.id)];
    if (answer === undefined) continue;
    for (const rule of q.deduction_rules) {
      if (rule.is_disqualifying || rule.option_value !== answer) continue;
      const value = Number(rule.deduction_value);
      price -= rule.deduction_type === "percentage" ? basePrice * (value / 100) : value;
    }
  }
  return Math.max(price, 0);
}

export function formatEur(amount: number | string | null): string {
  if (amount === null) return "—";
  const n = typeof amount === "string" ? Number(amount) : amount;
  return new Intl.NumberFormat("en-NL", { style: "currency", currency: "EUR" }).format(n);
}

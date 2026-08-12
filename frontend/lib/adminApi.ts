const API_URL = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";
const TOKEN_KEY = "tradein_admin_token";

export type AdminDevice = {
  id: string;
  brand: string;
  model: string;
  storage_gb: number;
  color: string | null;
  category: string;
  has_s_pen: boolean;
  slug: string;
  image_url: string | null;
  is_active: boolean;
  base_price: string | null;
  markup_pct: string | null;
  liquidity_tier: string | null;
  last_synced_at: string | null;
};

export type AdminQuestionSet = {
  id: number;
  category: string;
  brand: string | null;
  name: string;
  question_count: number;
};

export type AdminDeductionRule = {
  id: number;
  question_id: number;
  option_value: string;
  deduction_type: "fixed" | "percentage";
  deduction_value: string;
  is_disqualifying: boolean;
  disqualify_status: "rejected" | "manual_review" | null;
};

export type AdminQuestion = {
  id: number;
  question_set_id: number;
  text: string;
  type: string;
  display_order: number;
  options: { label: string; value: string }[];
  depends_on_question_id: number | null;
  depends_on_value: string | null;
  requires_device_attribute: string | null;
  deduction_rules: AdminDeductionRule[];
};

export function getToken(): string | null {
  if (typeof window === "undefined") return null;
  return window.localStorage.getItem(TOKEN_KEY);
}

export function setToken(token: string) {
  window.localStorage.setItem(TOKEN_KEY, token);
}

export function clearToken() {
  window.localStorage.removeItem(TOKEN_KEY);
}

/** Thrown on 401 so callers can redirect to login instead of showing an error. */
export class UnauthorizedError extends Error {}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const token = getToken();
  const res = await fetch(`${API_URL}/api/v1/admin${path}`, {
    ...init,
    headers: {
      "Content-Type": "application/json",
      ...(token ? { Authorization: `Bearer ${token}` } : {}),
      ...init?.headers,
    },
    cache: "no-store",
  });

  if (res.status === 401) {
    clearToken();
    throw new UnauthorizedError("Session expired — please sign in again.");
  }
  if (!res.ok) {
    const body = await res.json().catch(() => ({}));
    throw new Error(
      typeof body.detail === "string" ? body.detail : `Request failed: ${res.status}`
    );
  }
  return res.status === 204 ? (undefined as T) : res.json();
}

export async function login(email: string, password: string) {
  const res = await fetch(`${API_URL}/api/v1/admin/auth/login`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ email, password }),
  });
  if (!res.ok) {
    const body = await res.json().catch(() => ({}));
    throw new Error(body.detail ?? "Login failed");
  }
  const data = await res.json();
  setToken(data.access_token);
  return data as { email: string; can_view_payouts: boolean };
}

export const me = () => request<{ email: string; can_view_payouts: boolean }>("/auth/me");

export function listDevices(params: { brand?: string; search?: string } = {}) {
  const qs = new URLSearchParams();
  if (params.brand) qs.set("brand", params.brand);
  if (params.search) qs.set("search", params.search);
  return request<AdminDevice[]>(`/devices${qs.toString() ? `?${qs}` : ""}`);
}

export const updateDevice = (id: string, patch: Partial<AdminDevice>) =>
  request<AdminDevice>(`/devices/${id}`, { method: "PUT", body: JSON.stringify(patch) });

export const deactivateDevice = (id: string) =>
  request<void>(`/devices/${id}`, { method: "DELETE" });

export const updateBasePrice = (
  id: string,
  body: { base_price: string; markup_pct: string; liquidity_tier: string }
) => request<AdminDevice>(`/devices/${id}/base-price`, { method: "PUT", body: JSON.stringify(body) });

export const listQuestionSets = () => request<AdminQuestionSet[]>("/question-sets");

export const listQuestions = (questionSetId?: number) =>
  request<AdminQuestion[]>(
    `/questions${questionSetId ? `?question_set_id=${questionSetId}` : ""}`
  );

export const updateQuestion = (id: number, patch: Partial<AdminQuestion>) =>
  request<AdminQuestion>(`/questions/${id}`, { method: "PUT", body: JSON.stringify(patch) });

export const updateDeductionRule = (
  id: number,
  body: Omit<AdminDeductionRule, "id" | "question_id">
) => request<AdminDeductionRule>(`/deduction-rules/${id}`, {
  method: "PUT",
  body: JSON.stringify(body),
});

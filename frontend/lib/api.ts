const API_URL = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";

export type DeviceSummary = {
  id: string;
  brand: "apple" | "samsung";
  model: string;
  storage_gb: number;
  color: string | null;
  slug: string;
  image_url: string | null;
  has_s_pen: boolean;
  price_up_to: string | null;
};

export type DeductionRule = {
  option_value: string;
  deduction_type: "fixed" | "percentage";
  deduction_value: string;
  is_disqualifying: boolean;
  disqualify_status: "rejected" | "manual_review" | null;
};

export type Question = {
  id: number;
  text: string;
  type: "single_select" | "multi_select" | "boolean" | "device_selector";
  display_order: number;
  options: { label: string; value: string }[];
  depends_on_question_id: number | null;
  depends_on_value: string | null;
  requires_device_attribute: string | null;
  deduction_rules: DeductionRule[];
};

export type DeviceDetail = DeviceSummary & {
  storage_variants: DeviceSummary[];
  questions: Question[];
};

export type Quote = {
  id: string;
  device_id: string;
  answers: Record<string, string>;
  answers_detail: {
    question_id: number;
    question_text: string;
    selected_value: string;
    selected_label: string;
  }[];
  status: "pending" | "confirmed" | "expired" | "inspected" | "paid" | "manual_review" | "rejected";
  base_price_at_quote: string;
  calculated_price: string | null;
  fulfillment_method: "store" | "courier" | null;
  store_id: number | null;
  customer_name: string | null;
  customer_email: string | null;
  customer_phone: string | null;
  valid_until: string;
};

export type Store = {
  id: number;
  name: string;
  address_line: string;
  city: string;
  postal_code: string;
  lat: number;
  lng: number;
  opening_hours: Record<string, string>;
  is_active: boolean;
};

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const res = await fetch(`${API_URL}${path}`, {
    ...init,
    headers: { "Content-Type": "application/json", ...init?.headers },
    cache: "no-store",
  });
  if (!res.ok) {
    const body = await res.json().catch(() => ({}));
    throw new Error(body.detail ?? `Request failed: ${res.status}`);
  }
  return res.json();
}

export function listDevices(params: { brand?: string; search?: string } = {}) {
  const qs = new URLSearchParams();
  if (params.brand) qs.set("brand", params.brand);
  if (params.search) qs.set("search", params.search);
  const suffix = qs.toString() ? `?${qs.toString()}` : "";
  return request<DeviceSummary[]>(`/api/v1/devices${suffix}`);
}

export function getDevice(slug: string) {
  return request<DeviceDetail>(`/api/v1/devices/${slug}`);
}

export function createQuote(deviceId: string, answers: Record<string, string>) {
  return request<Quote>(`/api/v1/quotes`, {
    method: "POST",
    body: JSON.stringify({ device_id: deviceId, answers }),
  });
}

export function getQuote(id: string) {
  return request<Quote>(`/api/v1/quotes/${id}`);
}

export function confirmQuote(
  id: string,
  payload: {
    fulfillment_method: "store" | "courier";
    store_id?: number;
    customer_name: string;
    customer_email: string;
    customer_phone: string;
    iban: string;
    account_holder_name: string;
  }
) {
  return request<Quote>(`/api/v1/quotes/${id}/confirm`, {
    method: "POST",
    body: JSON.stringify(payload),
  });
}

export function listStores() {
  return request<Store[]>(`/api/v1/stores?limit=10`);
}

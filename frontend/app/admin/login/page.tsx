"use client";

import { useRouter } from "next/navigation";
import { useState } from "react";
import { login } from "@/lib/adminApi";
import { ShieldIcon } from "@/lib/icons";

export default function AdminLoginPage() {
  const router = useRouter();
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [submitting, setSubmitting] = useState(false);

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    setSubmitting(true);
    setError(null);
    try {
      await login(email, password);
      router.push("/admin/catalog");
    } catch (err: any) {
      setError(err.message);
      setSubmitting(false);
    }
  }

  return (
    <main className="flex min-h-screen items-center justify-center px-4">
      <form
        onSubmit={handleSubmit}
        className="w-full max-w-sm rounded-2xl border border-gray-200 bg-white p-8 shadow-card"
      >
        <div className="flex items-center gap-2">
          <span className="flex h-9 w-9 items-center justify-center rounded-lg bg-gradient-to-br from-brand-500 to-brand-700 text-white">
            <ShieldIcon className="h-5 w-5" />
          </span>
          <div>
            <h1 className="text-base font-bold text-gray-900">TradeIn Admin</h1>
            <p className="text-xs text-gray-500">Staff sign-in</p>
          </div>
        </div>

        <label className="mt-6 block text-sm">
          <span className="mb-1.5 block font-medium text-gray-800">Email</span>
          <input
            type="email"
            required
            autoComplete="username"
            value={email}
            onChange={(e) => setEmail(e.target.value)}
            className="w-full rounded-xl border border-gray-200 px-3.5 py-2.5 shadow-soft transition focus:border-brand-400 focus:outline-none focus:ring-2 focus:ring-brand-100"
          />
        </label>

        <label className="mt-4 block text-sm">
          <span className="mb-1.5 block font-medium text-gray-800">Password</span>
          <input
            type="password"
            required
            autoComplete="current-password"
            value={password}
            onChange={(e) => setPassword(e.target.value)}
            className="w-full rounded-xl border border-gray-200 px-3.5 py-2.5 shadow-soft transition focus:border-brand-400 focus:outline-none focus:ring-2 focus:ring-brand-100"
          />
        </label>

        {error && (
          <p className="mt-4 rounded-xl bg-red-50 px-3 py-2 text-sm text-red-700">{error}</p>
        )}

        <button
          type="submit"
          disabled={submitting}
          className="mt-6 w-full rounded-xl bg-gradient-to-r from-brand-600 to-brand-500 px-4 py-3 font-semibold text-white shadow-raised transition hover:brightness-105 active:scale-[0.99] disabled:cursor-not-allowed disabled:from-gray-300 disabled:to-gray-300 disabled:shadow-none"
        >
          {submitting ? "Signing in…" : "Sign in"}
        </button>
      </form>
    </main>
  );
}

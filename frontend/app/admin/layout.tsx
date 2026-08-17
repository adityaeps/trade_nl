"use client";

import Link from "next/link";
import { usePathname, useRouter } from "next/navigation";
import { useEffect, useState } from "react";
import { clearToken, getToken, me } from "@/lib/adminApi";
import { ShieldIcon } from "@/lib/icons";

const NAV = [
  { href: "/admin/catalog", label: "Catalog" },
  { href: "/admin/pricing", label: "Pricing" },
  { href: "/admin/questions", label: "Questions" },
  { href: "/admin/orders", label: "Orders" },
  // Hidden unless the account carries the payouts permission (§5). This is
  // presentation only - the API enforces it with a 403 regardless.
  { href: "/admin/payouts", label: "Payouts", requiresPayouts: true },
];

export default function AdminLayout({ children }: { children: React.ReactNode }) {
  const pathname = usePathname();
  const router = useRouter();
  const isLoginPage = pathname === "/admin/login";
  const [email, setEmail] = useState<string | null>(null);
  const [canViewPayouts, setCanViewPayouts] = useState(false);
  const [checking, setChecking] = useState(!isLoginPage);

  // Verifies the session and loads the signed-in admin's info. Keyed on
  // isLoginPage rather than pathname: this used to re-run on every
  // navigation between /admin/catalog, /admin/pricing, etc (pathname
  // changes on each), which re-fetched GET /auth/me and - because
  // `checking` blanks the whole shell below - flashed the entire admin
  // panel to a spinner on every single nav-link click. It only needs to
  // run once per session (mount) and again if the login/logged-in state
  // flips, e.g. router.push("/admin/catalog") straight after login.
  useEffect(() => {
    if (isLoginPage) {
      setChecking(false);
      return;
    }
    // Client-side gate only. The real enforcement is the JWT check on every
    // admin API route — this just avoids rendering a shell the user can't
    // populate, and bounces expired sessions back to login.
    if (!getToken()) {
      router.replace("/admin/login");
      return;
    }
    me()
      .then((u) => {
        setEmail(u.email);
        setCanViewPayouts(u.can_view_payouts);
      })
      .catch(() => router.replace("/admin/login"))
      .finally(() => setChecking(false));
  }, [isLoginPage, router]);

  // Bare `/admin` is a link people bookmark or type with no content of its
  // own - bounce it to the catalog. Kept separate from the session check
  // above (reads the already-fetched `checking` state rather than causing
  // one) so visiting it doesn't force a re-check of the session, and stays
  // the single owner of this redirect - see app/admin/page.tsx, where two
  // components both calling router.replace() raced and crashed.
  useEffect(() => {
    if (pathname === "/admin" && !checking && getToken()) {
      router.replace("/admin/catalog");
    }
  }, [pathname, checking, router]);

  if (isLoginPage) return <>{children}</>;

  if (checking) {
    return (
      <div className="flex min-h-screen items-center justify-center">
        <div className="h-6 w-6 animate-spin rounded-full border-2 border-gray-200 border-t-brand-500" />
      </div>
    );
  }

  return (
    <div className="min-h-screen">
      <header className="sticky top-0 z-20 border-b border-gray-200/70 bg-white/85 backdrop-blur-md">
        <div className="mx-auto flex max-w-6xl items-center gap-6 px-4 py-3 sm:px-6">
          <Link href="/admin/catalog" className="flex items-center gap-2">
            <span className="flex h-8 w-8 items-center justify-center rounded-lg bg-gradient-to-br from-brand-500 to-brand-700 text-white">
              <ShieldIcon className="h-[18px] w-[18px]" />
            </span>
            <span className="text-[15px] font-bold tracking-tight text-gray-900">
              TradeIn <span className="text-brand-600">Admin</span>
            </span>
          </Link>

          <nav className="flex gap-1">
            {NAV.filter((item) => !item.requiresPayouts || canViewPayouts).map((item) => (
              <Link
                key={item.href}
                href={item.href}
                className={`rounded-lg px-3 py-1.5 text-sm font-medium transition ${
                  pathname === item.href
                    ? "bg-brand-50 text-brand-700"
                    : "text-gray-500 hover:bg-gray-100 hover:text-gray-800"
                }`}
              >
                {item.label}
              </Link>
            ))}
          </nav>

          <div className="ml-auto flex items-center gap-3">
            <span className="hidden text-xs text-gray-500 sm:inline">{email}</span>
            <button
              onClick={() => {
                clearToken();
                router.replace("/admin/login");
              }}
              className="rounded-lg border border-gray-200 px-3 py-1.5 text-sm font-medium text-gray-600 transition hover:border-gray-300 hover:text-gray-900"
            >
              Sign out
            </button>
          </div>
        </div>
      </header>
      {children}
    </div>
  );
}

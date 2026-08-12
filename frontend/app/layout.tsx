import type { Metadata } from "next";
import { Inter } from "next/font/google";
import "./globals.css";

const inter = Inter({ subsets: ["latin"], variable: "--font-inter", display: "swap" });

// TODO(assumption): UI language (English vs Dutch vs both) is an open
// business decision per ARCHITECTURE.md §11 / TASKS.md Sprint 0. Building in
// English as a placeholder until confirmed — do not add i18n scaffolding
// speculatively.
export const metadata: Metadata = {
  title: "Sell your phone",
  description: "Get a price for your used Apple or Samsung phone.",
};

export default function RootLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  return (
    <html lang="en" className={inter.variable}>
      {/* Header lives in the (customer) route group's layout, not here -
          the admin panel has its own chrome and shouldn't inherit the
          customer-facing nav. */}
      <body className="min-h-screen font-sans text-gray-900">{children}</body>
    </html>
  );
}

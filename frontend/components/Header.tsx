import Link from "next/link";
import { ShieldIcon } from "@/lib/icons";

export default function Header() {
  return (
    <header className="sticky top-0 z-20 border-b border-gray-200/70 bg-white/80 backdrop-blur-md">
      <div className="mx-auto flex max-w-5xl items-center justify-between px-4 py-3.5 sm:px-6">
        <Link href="/" className="flex items-center gap-2">
          <span className="flex h-8 w-8 items-center justify-center rounded-lg bg-gradient-to-br from-brand-500 to-brand-700 text-white shadow-soft">
            <ShieldIcon className="h-[18px] w-[18px]" />
          </span>
          <span className="text-[15px] font-bold tracking-tight text-gray-900">
            TradeIn<span className="text-brand-600">.nl</span>
          </span>
        </Link>
        <div className="hidden items-center gap-1.5 rounded-full bg-emerald-50 px-3 py-1 text-xs font-medium text-emerald-700 sm:flex">
          <span className="h-1.5 w-1.5 rounded-full bg-emerald-500" />
          Free instant estimate
        </div>
      </div>
    </header>
  );
}

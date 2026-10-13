"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";

const LINKS = [
  { href: "/", label: "Dashboard" },
  { href: "/inbox", label: "Inbox" },
  { href: "/orders", label: "Orders" },
  { href: "/approvals", label: "Approvals" },
  { href: "/try", label: "Try your own email" },
  { href: "/about", label: "How it works" },
  { href: "/trace", label: "Model calls" },
];

export function Nav() {
  const pathname = usePathname();
  const active = (href: string) => (href === "/" ? pathname === "/" : pathname.startsWith(href));
  return (
    <nav className="sticky top-0 z-10 border-b border-zinc-200 bg-white/95 backdrop-blur">
      <div className="mx-auto flex w-full max-w-6xl flex-wrap items-center gap-x-1 gap-y-1 px-6 py-2.5 text-sm">
        <Link href="/" className="mr-4 flex items-center gap-2 text-base font-semibold">
          <span className="inline-flex h-6 w-6 items-center justify-center rounded bg-emerald-600 text-xs font-bold text-white">
            EA
          </span>
          ExportAgent
        </Link>
        {LINKS.map((link) => (
          <Link
            key={link.href}
            href={link.href}
            className={`rounded-md px-2.5 py-1.5 ${
              active(link.href) ? "bg-zinc-100 font-medium text-zinc-900" : "text-zinc-600 hover:text-zinc-900"
            }`}
          >
            {link.label}
          </Link>
        ))}
      </div>
    </nav>
  );
}

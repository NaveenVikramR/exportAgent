import type { Metadata } from "next";
import { Geist, Geist_Mono } from "next/font/google";
import Link from "next/link";
import "./globals.css";

const geistSans = Geist({
  variable: "--font-geist-sans",
  subsets: ["latin"],
});

const geistMono = Geist_Mono({
  variable: "--font-geist-mono",
  subsets: ["latin"],
});

export const metadata: Metadata = {
  title: "ExportAgent",
  description: "AI export desk for apparel and textile exporters",
};

export default function RootLayout({ children }: LayoutProps<"/">) {
  return (
    <html
      lang="en"
      className={`${geistSans.variable} ${geistMono.variable} h-full antialiased`}
    >
      <body className="min-h-full flex flex-col bg-zinc-50 text-zinc-900">
        <nav className="border-b border-zinc-200 bg-white">
          <div className="mx-auto flex w-full max-w-5xl items-center gap-6 px-6 py-3 text-sm">
            <Link href="/" className="text-base font-semibold">
              ExportAgent
            </Link>
            <Link href="/" className="text-zinc-600 hover:text-zinc-900">
              Inbox
            </Link>
            <Link href="/orders" className="text-zinc-600 hover:text-zinc-900">
              Orders
            </Link>
            <Link href="/trace" className="text-zinc-600 hover:text-zinc-900">
              Agent trace
            </Link>
          </div>
        </nav>
        {children}
      </body>
    </html>
  );
}

import type { Metadata } from "next";
import { Geist, Geist_Mono } from "next/font/google";
import { Nav } from "@/components/nav";
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
  title: "ExportAgent: AI export desk for apparel exporters",
  description:
    "Reads buyer POs, catches risky changes, drafts the reply and the export documents. NVIDIA Nemotron on Nebius Token Factory.",
};

export default function RootLayout({ children }: LayoutProps<"/">) {
  return (
    <html
      lang="en"
      className={`${geistSans.variable} ${geistMono.variable} h-full antialiased`}
    >
      <body className="min-h-full flex flex-col bg-zinc-50 text-zinc-900">
        <Nav />
        <div className="flex-1">{children}</div>
        <footer className="border-t border-zinc-200 bg-white">
          <div className="mx-auto flex w-full max-w-6xl flex-wrap justify-between gap-2 px-6 py-4 text-xs text-zinc-500">
            <span>ExportAgent · built for the Nebius × NVIDIA hackathon · MIT licence</span>
            <span>NVIDIA Nemotron Nano / Super / Ultra on Nebius Token Factory · Tavily for web checks</span>
          </div>
        </footer>
      </body>
    </html>
  );
}

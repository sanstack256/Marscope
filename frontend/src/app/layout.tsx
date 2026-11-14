import type { Metadata } from "next";
import "./globals.css";
import { Sidebar } from "../components/Sidebar";
import { TopNav } from "../components/TopNav";

export const metadata: Metadata = {
  title: "MARSCOPE — Martian Surface Intelligence & Exploration System",
  description:
    "Integrated Martian surface intelligence platform combining NASA planetary datasets, physics calculations, and constrained route optimization.",
};

export default function RootLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  return (
    <html lang="en" className="h-full antialiased dark">
      <body className="h-full bg-[#0b0d13] text-slate-100 flex overflow-hidden">
        {/* Navigation Sidebar */}
        <Sidebar />

        {/* Primary Viewport Area */}
        <div className="flex-1 flex flex-col min-w-0 overflow-hidden">
          <TopNav />
          <main className="flex-1 overflow-y-auto p-6 md:p-8 bg-[#0b0d13]">
            {children}
          </main>
        </div>
      </body>
    </html>
  );
}

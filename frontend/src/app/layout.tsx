import type { Metadata } from "next";
import "./globals.css";
import { AppShellClient } from "../components/AppShellClient";

export const metadata: Metadata = {
  title: "MARSCOPE | Mars Surface Exploration & Multi-Astronaut Operations",
  description:
    "Uncertainty-aware Mars surface exploration, multi-astronaut collaboration, emergency response, landing-site intelligence, and orbital terrain analysis.",
};

export default function RootLayout({
  children,
}: Readonly<{
  children: React.ReactNode;
}>) {
  return (
    <html lang="en" className="dark">
      <body className="antialiased bg-[var(--bg-canvas)] text-[var(--text-primary)] min-h-screen flex overflow-hidden">
        <AppShellClient>{children}</AppShellClient>
      </body>
    </html>
  );
}

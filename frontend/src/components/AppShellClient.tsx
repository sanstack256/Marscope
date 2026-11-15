"use client";

import React, { useEffect } from "react";
import { usePathname, useRouter } from "next/navigation";
import { useAuthMissionStore } from "../stores/useAuthMissionStore";
import { Sidebar } from "./Sidebar";
import { TopNav } from "./TopNav";
import { IntegratedMissionContextBar } from "./IntegratedMissionContextBar";
import { EmergencySosOverlay } from "./EmergencySosOverlay";
import { DemoTourOverlay } from "./DemoTourOverlay";

const PUBLIC_ROUTES = new Set(["/", "/login", "/register"]);

export function AppShellClient({ children }: { children: React.ReactNode }) {
  const pathname = usePathname();
  const router = useRouter();
  const isPublicRoute = PUBLIC_ROUTES.has(pathname);

  const checkSession = useAuthMissionStore((s) => s.checkSession);
  const authChecked = useAuthMissionStore((s) => s.authChecked);
  const authenticated = useAuthMissionStore((s) => s.authenticated);
  const activeMissionId = useAuthMissionStore((s) => s.activeMissionId);
  const connectMissionStream = useAuthMissionStore((s) => s.connectMissionStream);
  const setBrowserOnline = useAuthMissionStore((s) => s.setBrowserOnline);

  useEffect(() => {
    void checkSession();
  }, [checkSession]);

  useEffect(() => {
    setBrowserOnline(typeof navigator !== "undefined" ? navigator.onLine : true);
    const onOnline = () => setBrowserOnline(true);
    const onOffline = () => setBrowserOnline(false);
    window.addEventListener("online", onOnline);
    window.addEventListener("offline", onOffline);
    return () => {
      window.removeEventListener("online", onOnline);
      window.removeEventListener("offline", onOffline);
    };
  }, [setBrowserOnline]);

  useEffect(() => {
    if (!authenticated || !activeMissionId) return;
    return connectMissionStream(activeMissionId);
  }, [authenticated, activeMissionId, connectMissionStream]);

  useEffect(() => {
    if (!isPublicRoute && authChecked && !authenticated) {
      const safeNext = pathname && pathname.startsWith("/") && !pathname.startsWith("//") ? pathname : "/mission-control";
      router.replace(`/login?next=${encodeURIComponent(safeNext)}`);
    }
  }, [isPublicRoute, authChecked, authenticated, pathname, router]);

  if (isPublicRoute) {
    return <div className="w-full min-h-screen overflow-y-auto bg-[#050505] text-white">{children}</div>;
  }

  if (!authChecked || !authenticated) {
    return (
      <div className="w-full h-screen flex items-center justify-center bg-[#050505] text-[#A1A1AA] text-xs font-mono">
        Verifying MARSCOPE astronaut session...
      </div>
    );
  }

  return (
    <>
      <Sidebar />
      <div className="flex-1 flex flex-col min-w-0 h-screen overflow-hidden">
        <TopNav />
        <IntegratedMissionContextBar />
        <main className="flex-1 overflow-y-auto p-4 lg:p-6 bg-[var(--bg-canvas)]">
          {children}
        </main>
      </div>
      <EmergencySosOverlay />
      <DemoTourOverlay />
    </>
  );
}

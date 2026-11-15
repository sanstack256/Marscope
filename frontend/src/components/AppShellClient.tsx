"use client";

import React, { useEffect } from "react";
import { useAuthMissionStore } from "../stores/useAuthMissionStore";
import { Sidebar } from "./Sidebar";
import { TopNav } from "./TopNav";
import { IntegratedMissionContextBar } from "./IntegratedMissionContextBar";
import { EmergencySosOverlay } from "./EmergencySosOverlay";

export function AppShellClient({ children }: { children: React.ReactNode }) {
  const checkSession = useAuthMissionStore((s) => s.checkSession);
  const authenticated = useAuthMissionStore((s) => s.authenticated);
  const activeMissionId = useAuthMissionStore((s) => s.activeMissionId);
  const connectMissionStream = useAuthMissionStore((s) => s.connectMissionStream);
  const setBrowserOnline = useAuthMissionStore((s) => s.setBrowserOnline);

  useEffect(() => {
    void checkSession();
  }, [checkSession]);

  useEffect(() => {
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
    </>
  );
}

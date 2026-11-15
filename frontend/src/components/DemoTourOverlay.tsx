"use client";

import React, { useEffect, useState } from "react";
import { usePathname, useRouter } from "next/navigation";
import { ChevronLeft, ChevronRight, Compass, X } from "lucide-react";
import { useAuthMissionStore } from "../stores/useAuthMissionStore";

export interface DemoTourStep {
  step: number;
  title: string;
  route: string;
  summary: string;
  checklist: string[];
}

export const DEMO_TOUR_STEPS: DemoTourStep[] = [
  {
    step: 1,
    title: "Mission Overview",
    route: "/mission-control",
    summary:
      "Review the Gale Crater demonstration mission, its three demo astronauts, active SOS alert, and available scientific context.",
    checklist: [
      "Verify DEMO MODE badge and 3 demo crew members",
      "Notice Alpha's active SOS banner and mission activity feed",
    ],
  },
  {
    step: 2,
    title: "Crew & Positions",
    route: "/crew",
    summary:
      "Inspect persisted IAU2000:49900 coordinates for Demo Commander, Alpha, and Bravo along with source classification and freshness.",
    checklist: [
      "Inspect Alpha & Bravo coordinates inside Gale Crater",
      "Verify USER_PROVIDED provenance and connection status",
    ],
  },
  {
    step: 3,
    title: "Emergency Response",
    route: "/emergency",
    summary:
      "Open DEMO ASTRONAUT ALPHA's active SOS, inspect the reported position and timestamp, acknowledge it, and observe persisted history.",
    checklist: [
      "Inspect Alpha's SOS location and authenticated-channel notice",
      "Click Acknowledge or Resolve to persist a real transition",
    ],
  },
  {
    step: 4,
    title: "Field Observations",
    route: "/observations",
    summary:
      "Inspect mineral & material reports from Alpha and Bravo, each labeled USER_REPORTED — DEMONSTRATION DATA with CRS coordinates.",
    checklist: [
      "Select Alpha's sulfate veinlet report or Bravo's basaltic float report",
      "Use Focus on Map / 3D View to synchronize spatial focus",
    ],
  },
  {
    step: 5,
    title: "Mars Globe & 2D Map",
    route: "/explorer",
    summary:
      "Explore the interactive Mars globe and 3D terrain scene, toggle available orbital layers, and inspect persisted spatial markers.",
    checklist: [
      "Switch between 3D Terrain DEM, Split View, and Mars Globe",
      "Verify coordinates use IAU2000:49900 planetocentric frame",
    ],
  },
  {
    step: 6,
    title: "Terrain Intelligence",
    route: "/terrain",
    summary:
      "Inspect real processed HiRISE Stereo DTM (1.01 m/px) and MOLA MEGDR elevation, slope, and roughness derivatives.",
    checklist: [
      "Review dataset resolution suitability and NoData boundaries",
      "Verify missing local terrain is never fabricated",
    ],
  },
  {
    step: 7,
    title: "Scientific Intelligence",
    route: "/evidence",
    summary:
      "Inspect the Evidence Intelligence & Composition HUD, distinguishing NASA PDS archive measurements from user-reported demo notes.",
    checklist: [
      "Inspect APXS/ChemCam/CheMin archive evidence provenance",
      "Confirm unavailable instrument data stays explicitly unavailable",
    ],
  },
  {
    step: 8,
    title: "Mission Planning & EVA Ops",
    route: "/planner",
    summary:
      "Evaluate terrain-aware routes and EVA constraints under explicit USER_ASSUMED inputs without unvalidated safety certification.",
    checklist: [
      "Inspect slope limits, climb work, and configured assumptions",
      "Also visit /eva-operations or /active-navigation for live execution",
    ],
  },
];

const TOUR_STORAGE_KEY = "marscope_demo_tour_state";

export function startDemoTour(step = 0): void {
  if (typeof window === "undefined") return;
  try {
    window.localStorage.setItem(TOUR_STORAGE_KEY, JSON.stringify({ active: true, step }));
  } catch {
    // ignore storage errors
  }
  window.dispatchEvent(new CustomEvent("marscope:start-demo-tour", { detail: { step } }));
}

export function DemoTourOverlay() {
  const router = useRouter();
  const pathname = usePathname();
  const authenticated = useAuthMissionStore((s) => s.authenticated);
  const astronaut = useAuthMissionStore((s) => s.astronaut);

  const [active, setActive] = useState(false);
  const [stepIndex, setStepIndex] = useState(0);

  useEffect(() => {
    const raf = window.requestAnimationFrame(() => {
      try {
        const raw = window.localStorage.getItem(TOUR_STORAGE_KEY);
        if (raw) {
          const parsed = JSON.parse(raw);
          if (parsed && typeof parsed.active === "boolean") {
            setActive(parsed.active);
            if (typeof parsed.step === "number") {
              setStepIndex(Math.max(0, Math.min(DEMO_TOUR_STEPS.length - 1, parsed.step)));
            }
          }
        }
      } catch {
        // ignore
      }
    });

    const onStart = (ev: Event) => {
      const detail = (ev as CustomEvent<{ step?: number }>).detail;
      const nextStep = typeof detail?.step === "number" ? detail.step : 0;
      setActive(true);
      setStepIndex(nextStep);
    };
    window.addEventListener("marscope:start-demo-tour", onStart);
    return () => {
      window.cancelAnimationFrame(raf);
      window.removeEventListener("marscope:start-demo-tour", onStart);
    };
  }, []);

  if (!authenticated || !astronaut?.is_demo || !active) {
    return null;
  }

  const current = DEMO_TOUR_STEPS[stepIndex] || DEMO_TOUR_STEPS[0];

  const updateStep = (nextIdx: number) => {
    const clamped = Math.max(0, Math.min(DEMO_TOUR_STEPS.length - 1, nextIdx));
    setStepIndex(clamped);
    try {
      window.localStorage.setItem(TOUR_STORAGE_KEY, JSON.stringify({ active: true, step: clamped }));
    } catch {
      // ignore
    }
    const targetRoute = DEMO_TOUR_STEPS[clamped].route;
    if (pathname !== targetRoute) {
      router.push(targetRoute);
    }
  };

  const exitTour = () => {
    setActive(false);
    try {
      window.localStorage.setItem(TOUR_STORAGE_KEY, JSON.stringify({ active: false, step: stepIndex }));
    } catch {
      // ignore
    }
  };

  return (
    <aside
      aria-label="Guided Demo Tour"
      className="fixed bottom-4 left-4 right-4 sm:left-auto sm:right-20 sm:w-[390px] z-40 rounded-[8px] border border-[#FF6A1A]/60 bg-[#0B0B0B]/95 shadow-2xl p-4 text-xs text-white"
    >
      <div className="flex items-center justify-between gap-2 mb-2">
        <div className="flex items-center gap-2">
          <Compass className="w-4 h-4 text-[#FF6A1A]" />
          <span className="font-mono text-[10px] uppercase tracking-wider px-1.5 py-0.5 rounded-[4px] bg-[#FF6A1A]/20 border border-[#FF6A1A]/50 text-[#FF6A1A] font-bold">
            GUIDED TOUR • {current.step} / {DEMO_TOUR_STEPS.length}
          </span>
        </div>
        <button
          type="button"
          onClick={exitTour}
          aria-label="Exit guided tour"
          className="p-1 rounded-[4px] text-[#A1A1AA] hover:text-white hover:bg-white/10"
        >
          <X className="w-3.5 h-3.5" />
        </button>
      </div>

      <h3 className="text-sm font-semibold text-white">{current.title}</h3>
      <p className="mt-1 text-[12px] text-[#A1A1AA] leading-relaxed">{current.summary}</p>

      <ul className="mt-2.5 space-y-1 text-[11px] text-[#D4D4D8]">
        {current.checklist.map((item) => (
          <li key={item} className="flex items-start gap-1.5">
            <span className="text-[#FF6A1A] mt-0.5">•</span>
            <span>{item}</span>
          </li>
        ))}
      </ul>

      <div className="mt-3 pt-2.5 border-t border-[#242424] flex items-center justify-between gap-2">
        <button
          type="button"
          onClick={() => updateStep(stepIndex - 1)}
          disabled={stepIndex === 0}
          className="inline-flex items-center gap-1 px-2.5 py-1.5 rounded-[4px] border border-[#242424] text-[#A1A1AA] hover:text-white disabled:opacity-40"
        >
          <ChevronLeft className="w-3.5 h-3.5" />
          <span>Prev</span>
        </button>

        {pathname !== current.route && (
          <button
            type="button"
            onClick={() => router.push(current.route)}
            className="px-2.5 py-1.5 rounded-[4px] border border-[#FF6A1A]/50 text-[#FF6A1A] hover:bg-[#FF6A1A]/10 font-mono text-[11px]"
          >
            Open {current.route}
          </button>
        )}

        {stepIndex < DEMO_TOUR_STEPS.length - 1 ? (
          <button
            type="button"
            onClick={() => updateStep(stepIndex + 1)}
            className="inline-flex items-center gap-1 px-3 py-1.5 rounded-[4px] bg-[#FF6A1A] hover:bg-[#FF7F32] text-white font-semibold"
          >
            <span>Next</span>
            <ChevronRight className="w-3.5 h-3.5" />
          </button>
        ) : (
          <button
            type="button"
            onClick={exitTour}
            className="px-3 py-1.5 rounded-[4px] bg-[#FF6A1A] hover:bg-[#FF7F32] text-white font-semibold"
          >
            Finish Tour
          </button>
        )}
      </div>
    </aside>
  );
}


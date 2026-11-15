"use client";

import React, { useState } from "react";
import Link from "next/link";
import dynamic from "next/dynamic";
import { ArrowRight, Check, Menu, X } from "lucide-react";
import { useAuthMissionStore } from "../stores/useAuthMissionStore";

const MarsLandingGlobe = dynamic(
  () => import("../components/landing/MarsLandingGlobe").then((m) => m.MarsLandingGlobe),
  {
    ssr: false,
    loading: () => (
      <div className="w-full aspect-square max-w-[520px] mx-auto rounded-full border border-[#242424] bg-[#0B0B0B] flex items-center justify-center text-xs font-mono text-[#A1A1AA]">
        Initializing 3D Mars...
      </div>
    ),
  }
);

export default function LandingPage() {
  const authenticated = useAuthMissionStore((s) => s.authenticated);
  const astronaut = useAuthMissionStore((s) => s.astronaut);
  const [mobileMenuOpen, setMobileMenuOpen] = useState(false);

  return (
    <div className="min-h-screen bg-[#050505] text-white selection:bg-[#FF6A1A] selection:text-white">
      {/* Minimal Sticky Navigation Bar */}
      <header className="sticky top-0 z-40 border-b border-[#242424] bg-[#050505]/90 backdrop-blur-md">
        <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 h-16 flex items-center justify-between gap-4">
          <Link href="/" className="flex items-center gap-3 min-w-0">
            {/* eslint-disable-next-line @next/next/no-img-element */}
            <img
              src="/brand-icon.png"
              alt="MARSCOPE"
              className="w-9 h-9 rounded-[6px] object-contain bg-black border border-[#242424] shrink-0"
            />
            <div className="min-w-0">
              <div className="text-sm font-bold tracking-[0.14em] text-white leading-none">MARSCOPE</div>
              <div className="text-[10px] font-mono tracking-[0.14em] text-[#A1A1AA] mt-1 truncate">
                MARTIAN SURFACE INTELLIGENCE
              </div>
            </div>
          </Link>

          <nav aria-label="Landing navigation" className="hidden md:flex items-center gap-7 text-xs text-[#A1A1AA]">
            <a href="#platform" className="hover:text-white transition-colors">
              Platform
            </a>
            <a href="#capabilities" className="hover:text-white transition-colors">
              Capabilities
            </a>
            <a href="#mission-planning" className="hover:text-white transition-colors">
              Mission Planning
            </a>
            <a href="#about" className="hover:text-white transition-colors">
              About
            </a>
          </nav>

          <div className="hidden sm:flex items-center gap-3 text-xs">
            {authenticated ? (
              <Link
                href="/mission-control"
                className="inline-flex items-center gap-1.5 px-4 py-2 rounded-[4px] bg-[#FF6A1A] hover:bg-[#FF7F32] text-white font-semibold transition-colors"
              >
                <span>{astronaut?.is_demo ? "OPEN DEMO MISSION" : "OPEN MARSCOPE"}</span>
                <ArrowRight className="w-3.5 h-3.5" />
              </Link>
            ) : (
              <>
                <Link
                  href="/login"
                  className="px-3.5 py-2 rounded-[4px] border border-[#242424] hover:border-[#A1A1AA] text-white font-medium transition-colors"
                >
                  Sign In
                </Link>
                <Link
                  href="/register"
                  className="px-4 py-2 rounded-[4px] bg-[#FF6A1A] hover:bg-[#FF7F32] text-white font-semibold transition-colors"
                >
                  Get Started
                </Link>
              </>
            )}
          </div>

          <div className="flex sm:hidden items-center gap-2">
            <Link
              href={authenticated ? "/mission-control" : "/login"}
              className="px-3 py-1.5 rounded-[4px] bg-[#FF6A1A] text-white text-xs font-semibold"
            >
              {authenticated ? "Open" : "Sign In"}
            </Link>
            <button
              type="button"
              onClick={() => setMobileMenuOpen((v) => !v)}
              aria-label="Toggle menu"
              className="p-2 rounded-[4px] border border-[#242424] text-[#A1A1AA] hover:text-white"
            >
              {mobileMenuOpen ? <X className="w-4 h-4" /> : <Menu className="w-4 h-4" />}
            </button>
          </div>
        </div>

        {mobileMenuOpen && (
          <div className="sm:hidden border-t border-[#242424] bg-[#0B0B0B] px-4 py-3 space-y-2 text-xs">
            <a href="#platform" onClick={() => setMobileMenuOpen(false)} className="block py-1.5 text-[#A1A1AA] hover:text-white">
              Platform
            </a>
            <a href="#capabilities" onClick={() => setMobileMenuOpen(false)} className="block py-1.5 text-[#A1A1AA] hover:text-white">
              Capabilities
            </a>
            <a href="#mission-planning" onClick={() => setMobileMenuOpen(false)} className="block py-1.5 text-[#A1A1AA] hover:text-white">
              Mission Planning
            </a>
            <a href="#about" onClick={() => setMobileMenuOpen(false)} className="block py-1.5 text-[#A1A1AA] hover:text-white">
              About
            </a>
            {!authenticated && (
              <div className="pt-2 flex gap-2 border-t border-[#242424]">
                <Link href="/login" className="flex-1 text-center py-2 rounded-[4px] border border-[#242424] text-white">
                  Sign In
                </Link>
                <Link href="/register" className="flex-1 text-center py-2 rounded-[4px] bg-[#FF6A1A] text-white font-semibold">
                  Get Started
                </Link>
              </div>
            )}
          </div>
        )}
      </header>

      {/* Hero Section — Two-Column with Interactive Rotating 3D Mars */}
      <section className="relative overflow-hidden border-b border-[#242424] bg-[#050505]">
        <div
          className="pointer-events-none absolute inset-0 opacity-[0.06]"
          style={{
            backgroundImage:
              "linear-gradient(to right, #FFFFFF 1px, transparent 1px), linear-gradient(to bottom, #FFFFFF 1px, transparent 1px)",
            backgroundSize: "64px 64px",
          }}
          aria-hidden="true"
        />

        <div className="relative max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 py-14 sm:py-20 lg:py-24 grid grid-cols-1 lg:grid-cols-12 gap-10 lg:gap-8 items-center">
          <div className="lg:col-span-6 space-y-6 z-10">
            <div className="inline-flex items-center gap-2 text-[11px] font-mono tracking-[0.18em] text-[#FF6A1A] uppercase">
              <span className="w-2 h-2 rounded-full bg-[#FF6A1A]" />
              <span>A NEW PERSPECTIVE ON MARTIAN EXPLORATION</span>
            </div>

            <h1 className="text-4xl sm:text-5xl lg:text-[54px] font-bold tracking-tight leading-[1.08] text-white">
              Explore Mars.{" "}
              <span className="text-[#FF6A1A]">Understand the terrain.</span>{" "}
              Plan the mission.
            </h1>

            <p className="text-base sm:text-lg text-[#A1A1AA] leading-relaxed max-w-xl">
              MARSCOPE brings Martian terrain intelligence, scientific evidence and human exploration
              planning into one integrated environment. Explore surface data, investigate geological targets
              and evaluate mission routes with transparent evidence and uncertainty.
            </p>

            <div className="flex flex-wrap items-center gap-3.5 pt-1">
              <Link
                href={authenticated ? "/mission-control" : "/register"}
                className="inline-flex items-center gap-2 px-6 py-3 rounded-[4px] bg-[#FF6A1A] hover:bg-[#FF7F32] text-white text-xs sm:text-sm font-semibold tracking-wider transition-colors"
              >
                <span>{authenticated ? "OPEN MARSCOPE" : "EXPLORE MARSCOPE"}</span>
                <ArrowRight className="w-4 h-4" />
              </Link>
              <Link
                href="/login?demo=1"
                className="inline-flex items-center gap-2 px-6 py-3 rounded-[4px] border border-[#242424] hover:border-white bg-[#0B0B0B] text-white text-xs sm:text-sm font-semibold tracking-wider transition-colors"
              >
                <span>VIEW DEMO</span>
              </Link>
            </div>

            <div className="pt-4 border-t border-[#242424] flex flex-wrap gap-x-6 gap-y-2 text-[11px] font-mono tracking-[0.12em] text-[#A1A1AA]">
              <span>PLANETARY INTELLIGENCE</span>
              <span className="text-[#FF6A1A]">•</span>
              <span>SCIENTIFIC DISCOVERY</span>
              <span className="text-[#FF6A1A]">•</span>
              <span>HUMAN-AWARE EXPLORATION</span>
            </div>
          </div>

          <div className="lg:col-span-6">
            <MarsLandingGlobe />
          </div>
        </div>
      </section>

      {/* Section 1 — Planetary Intelligence (#0B0B0B) */}
      <section id="platform" className="bg-[#0B0B0B] border-b border-[#242424] py-16 sm:py-24">
        <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 grid grid-cols-1 lg:grid-cols-12 gap-10 lg:gap-12 items-center">
          <div className="lg:col-span-6">
            <div className="rounded-[6px] border border-[#242424] bg-[#050505] overflow-hidden shadow-2xl">
              {/* eslint-disable-next-line @next/next/no-img-element */}
              <img
                src="/landing/section-planetary.png"
                alt="MARSCOPE 3D terrain DEM and orbital imagery explorer"
                className="w-full h-auto block object-cover"
              />
            </div>
          </div>

          <div className="lg:col-span-6 space-y-5">
            <div className="text-[11px] font-mono tracking-[0.16em] text-[#FF6A1A] uppercase">
              01 / PLANETARY INTELLIGENCE
            </div>
            <h2 className="text-3xl sm:text-4xl font-bold tracking-tight text-white leading-tight">
              Understand the surface beneath every step.
            </h2>
            <p className="text-sm sm:text-base text-[#A1A1AA] leading-relaxed">
              Bring Martian surface information together in a spatial environment. Explore terrain,
              elevation, imagery, coverage and available scientific datasets while keeping resolution,
              provenance and uncertainty visible.
            </p>
            <ul className="space-y-2.5 text-sm text-[#E4E4E7]">
              {[
                "Layered planetary datasets.",
                "Terrain and elevation intelligence.",
                "Spatial coverage and uncertainty.",
                "Integrated 2D and 3D exploration.",
              ].map((item) => (
                <li key={item} className="flex items-center gap-2.5">
                  <Check className="w-4 h-4 text-[#FF6A1A] shrink-0" />
                  <span>{item}</span>
                </li>
              ))}
            </ul>
            <div className="pt-2">
              <Link
                href={authenticated ? "/explorer" : "/login?demo=1"}
                className="inline-flex items-center gap-2 px-5 py-2.5 rounded-[4px] border border-[#FF6A1A] text-[#FF6A1A] hover:bg-[#FF6A1A] hover:text-white text-xs font-semibold tracking-wider transition-colors"
              >
                <span>EXPLORE PLANETARY INTELLIGENCE</span>
                <ArrowRight className="w-3.5 h-3.5" />
              </Link>
            </div>
          </div>
        </div>
      </section>

      {/* Section 2 — Scientific Discovery (#111111) */}
      <section id="capabilities" className="bg-[#111111] border-b border-[#242424] py-16 sm:py-24">
        <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 grid grid-cols-1 lg:grid-cols-12 gap-10 lg:gap-12 items-center">
          <div className="lg:col-span-6 space-y-5 order-2 lg:order-1">
            <div className="text-[11px] font-mono tracking-[0.16em] text-[#FF6A1A] uppercase">
              02 / SCIENTIFIC DISCOVERY
            </div>
            <h2 className="text-3xl sm:text-4xl font-bold tracking-tight text-white leading-tight">
              Turn observations into scientific questions.
            </h2>
            <p className="text-sm sm:text-base text-[#A1A1AA] leading-relaxed">
              Investigate Martian geological targets through available orbital and rover observations.
              Connect evidence, inspect competing interpretations and understand what is known, what remains
              uncertain and what needs further investigation.
            </p>
            <ul className="space-y-2.5 text-sm text-[#E4E4E7]">
              {[
                "Scientific evidence integration.",
                "Geological target exploration.",
                "Mineralogical and compositional context where supported by data.",
                "Evidence provenance and uncertainty.",
              ].map((item) => (
                <li key={item} className="flex items-center gap-2.5">
                  <Check className="w-4 h-4 text-[#FF6A1A] shrink-0" />
                  <span>{item}</span>
                </li>
              ))}
            </ul>
            <div className="pt-2">
              <Link
                href={authenticated ? "/evidence" : "/login?demo=1"}
                className="inline-flex items-center gap-2 px-5 py-2.5 rounded-[4px] border border-[#FF6A1A] text-[#FF6A1A] hover:bg-[#FF6A1A] hover:text-white text-xs font-semibold tracking-wider transition-colors"
              >
                <span>DISCOVER THE SCIENCE</span>
                <ArrowRight className="w-3.5 h-3.5" />
              </Link>
            </div>
          </div>

          <div className="lg:col-span-6 order-1 lg:order-2">
            <div className="rounded-[6px] border border-[#242424] bg-[#050505] overflow-hidden shadow-2xl">
              {/* eslint-disable-next-line @next/next/no-img-element */}
              <img
                src="/landing/section-science.png"
                alt="MARSCOPE NASA PDS imagery and scientific evidence catalogue"
                className="w-full h-auto block object-cover"
              />
            </div>
          </div>
        </div>
      </section>

      {/* Section 3 — Human Exploration and Mission Planning (#0B0B0B) */}
      <section id="mission-planning" className="bg-[#0B0B0B] border-b border-[#242424] py-16 sm:py-24">
        <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 grid grid-cols-1 lg:grid-cols-12 gap-10 lg:gap-12 items-center">
          <div className="lg:col-span-6">
            <div className="rounded-[6px] border border-[#242424] bg-[#050505] overflow-hidden shadow-2xl">
              {/* eslint-disable-next-line @next/next/no-img-element */}
              <img
                src="/landing/section-mission.png"
                alt="MARSCOPE terrain-aware EVA route planner"
                className="w-full h-auto block object-cover"
              />
            </div>
          </div>

          <div className="lg:col-span-6 space-y-5">
            <div className="text-[11px] font-mono tracking-[0.16em] text-[#FF6A1A] uppercase">
              03 / HUMAN EXPLORATION &amp; MISSION PLANNING
            </div>
            <h2 className="text-3xl sm:text-4xl font-bold tracking-tight text-white leading-tight">
              Plan exploration with the human mission in mind.
            </h2>
            <p className="text-sm sm:text-base text-[#A1A1AA] leading-relaxed">
              Connect terrain intelligence with exploration planning. Evaluate candidate routes, inspect
              terrain limitations, plan observation stops and assess outbound and return operations under
              explicit assumptions.
            </p>
            <ul className="space-y-2.5 text-sm text-[#E4E4E7]">
              {[
                "Human-aware terrain assessment.",
                "Route planning and comparison.",
                "EVA planning and return assessment.",
                "Crew collaboration and field observations.",
              ].map((item) => (
                <li key={item} className="flex items-center gap-2.5">
                  <Check className="w-4 h-4 text-[#FF6A1A] shrink-0" />
                  <span>{item}</span>
                </li>
              ))}
            </ul>
            <div className="pt-2">
              <Link
                href={authenticated ? "/planner" : "/login?demo=1"}
                className="inline-flex items-center gap-2 px-5 py-2.5 rounded-[4px] border border-[#FF6A1A] text-[#FF6A1A] hover:bg-[#FF6A1A] hover:text-white text-xs font-semibold tracking-wider transition-colors"
              >
                <span>PLAN A MARSWALK</span>
                <ArrowRight className="w-3.5 h-3.5" />
              </Link>
            </div>
          </div>
        </div>
      </section>

      {/* Final CTA */}
      <section className="bg-[#050505] border-b border-[#242424] py-20 sm:py-24">
        <div className="max-w-4xl mx-auto px-4 sm:px-6 lg:px-8 text-center space-y-6">
          <h2 className="text-3xl sm:text-5xl font-bold tracking-tight text-white">
            The next frontier needs <span className="text-[#FF6A1A]">better intelligence.</span>
          </h2>
          <p className="text-sm sm:text-base text-[#A1A1AA] max-w-2xl mx-auto">
            Explore the Martian surface through connected scientific evidence, spatial intelligence and
            human-aware mission planning.
          </p>
          <div className="flex flex-wrap items-center justify-center gap-4 pt-2">
            <Link
              href={authenticated ? "/mission-control" : "/login"}
              className="inline-flex items-center gap-2 px-6 py-3 rounded-[4px] bg-[#FF6A1A] hover:bg-[#FF7F32] text-white text-xs sm:text-sm font-semibold tracking-wider transition-colors"
            >
              <span>ENTER MARSCOPE</span>
              <ArrowRight className="w-4 h-4" />
            </Link>
            <Link
              href="/login?demo=1"
              className="inline-flex items-center gap-2 px-6 py-3 rounded-[4px] border border-[#242424] hover:border-white bg-[#0B0B0B] text-white text-xs sm:text-sm font-semibold tracking-wider transition-colors"
            >
              <span>TRY THE INTERACTIVE DEMO</span>
            </Link>
          </div>
        </div>
      </section>

      {/* Footer */}
      <footer id="about" className="bg-[#050505] py-12">
        <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 space-y-8">
          <div className="grid grid-cols-1 md:grid-cols-12 gap-8 text-xs text-[#A1A1AA]">
            <div className="md:col-span-5 space-y-2.5">
              <div className="text-sm font-bold tracking-[0.14em] text-white">MARSCOPE</div>
              <p className="leading-relaxed max-w-sm">
                Martian Surface Intelligence &amp; Exploration System unifying NASA PDS orbital terrain,
                scientific evidence provenance, and human EVA mission planning.
              </p>
              <p className="text-[11px] font-mono text-[#71717A]">
                Built for the NASA Space Apps Challenge (independent open-source project; not affiliated with or endorsed by NASA).
              </p>
            </div>

            <div className="md:col-span-3 space-y-2">
              <div className="font-mono text-[11px] uppercase tracking-wider text-white">Platform</div>
              <ul className="space-y-1.5">
                <li>
                  <Link href="/login" className="hover:text-white">
                    Sign In
                  </Link>
                </li>
                <li>
                  <Link href="/register" className="hover:text-white">
                    Astronaut Registration
                  </Link>
                </li>
                <li>
                  <Link href="/login?demo=1" className="hover:text-white">
                    Judge Demo Access
                  </Link>
                </li>
              </ul>
            </div>

            <div className="md:col-span-4 space-y-2">
              <div className="font-mono text-[11px] uppercase tracking-wider text-white">Resources</div>
              <ul className="space-y-1.5">
                <li>
                  <a
                    href="https://github.com/nssanjeev/Marscope"
                    target="_blank"
                    rel="noreferrer"
                    className="hover:text-white"
                  >
                    GitHub Repository
                  </a>
                </li>
                <li>
                  <span className="text-[#71717A]">Documentation: docs/ACTIVE_NAVIGATION.md, docs/FINAL_VALIDATION_REPORT.md</span>
                </li>
              </ul>
            </div>
          </div>

          <div className="pt-6 border-t border-[#242424] flex flex-col sm:flex-row sm:items-center sm:justify-between gap-4 text-[11px] text-[#71717A]">
            <p className="max-w-3xl leading-relaxed">
              MARSCOPE is an independent exploration decision-support project. Its outputs are subject to
              source-data availability, model assumptions and scientific limitations. It is not a
              flight-certified astronaut safety system.
            </p>
            <div className="shrink-0 font-mono">© 2026 MARSCOPE</div>
          </div>
        </div>
      </footer>
    </div>
  );
}

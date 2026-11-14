"use client";

import Link from "next/link";
import Image from "next/image";
import { usePathname } from "next/navigation";
import {
  LayoutDashboard,
  Globe2,
  Mountain,
  Telescope,
  Compass,
  GitCompare,
  PlayCircle,
  Database,
  Settings,
  ChevronRight,
} from "lucide-react";
import { APP_NAME } from "../lib/constants";

const ICON_MAP: Record<string, React.ElementType> = {
  "/": LayoutDashboard,
  "/explorer": Globe2,
  "/terrain": Mountain,
  "/targets": Telescope,
  "/planner": Compass,
  "/routes": GitCompare,
  "/simulation": PlayCircle,
  "/evidence": Database,
  "/settings": Settings,
};

const NAV_LINKS = [
  { name: "Mission Overview", href: "/" },
  { name: "Surface Explorer", href: "/explorer", badge: "3D" },
  { name: "Terrain Intelligence", href: "/terrain" },
  { name: "Target Explorer", href: "/targets" },
  { name: "Route Planner", href: "/planner", badge: "Core" },
  { name: "Route Comparison", href: "/routes" },
  { name: "Mission Simulation", href: "/simulation" },
  { name: "Evidence & Provenance", href: "/evidence" },
  { name: "Mission Assumptions", href: "/settings" },
];

export function Sidebar() {
  const pathname = usePathname();

  return (
    <aside className="w-64 bg-[#0d111a] border-r border-[#1e2638] flex flex-col shrink-0 select-none">
      {/* Brand Header */}
      <Link
        href="/"
        className="h-16 flex items-center px-5 border-b border-[#1e2638] gap-3 hover:bg-[#121723] transition-colors"
      >
        <div className="w-10 h-9 rounded-lg bg-[#0b0d13] border border-[#e25b38]/35 flex items-end justify-center overflow-hidden shadow-[0_0_15px_rgba(226,91,56,0.25)] shrink-0 px-0.5 pt-1.5">
          <Image
            src="/marscope-logo.png"
            alt="MARSCOPE Mars Horizon Logo"
            width={887}
            height={329}
            priority
            className="w-full h-auto object-contain"
          />
        </div>
        <div>
          <div className="text-base font-bold tracking-wider text-slate-100">{APP_NAME}</div>
          <div className="text-[10px] uppercase font-mono tracking-widest text-[#e25b38]">NASA Space Apps</div>
        </div>
      </Link>

      {/* Navigation List */}
      <nav className="flex-1 overflow-y-auto px-3 py-4 space-y-1">
        <div className="px-3 pb-2 text-[10px] font-mono uppercase tracking-wider text-slate-500">
          Navigation Systems
        </div>
        {NAV_LINKS.map((link) => {
          const isActive = pathname === link.href;
          const Icon = ICON_MAP[link.href] || Globe2;
          return (
            <Link
              key={link.href}
              href={link.href}
              className={`flex items-center justify-between px-3 py-2.5 rounded-lg text-xs font-medium transition-all group ${
                isActive
                  ? "bg-[#e25b38]/15 text-[#f16f4d] border border-[#e25b38]/30 shadow-[0_0_12px_rgba(226,91,56,0.15)]"
                  : "text-slate-400 hover:text-slate-200 hover:bg-[#161c2b] border border-transparent"
              }`}
            >
              <div className="flex items-center gap-3">
                <Icon className={`w-4 h-4 ${isActive ? "text-[#e25b38]" : "text-slate-500 group-hover:text-slate-300"}`} />
                <span>{link.name}</span>
              </div>
              <div className="flex items-center gap-1.5">
                {link.badge && (
                  <span
                    className={`text-[9px] px-1.5 py-0.5 rounded font-mono font-semibold uppercase ${
                      isActive
                        ? "bg-[#e25b38]/20 text-[#f16f4d]"
                        : "bg-slate-800 text-slate-400 group-hover:bg-slate-700"
                    }`}
                  >
                    {link.badge}
                  </span>
                )}
                {isActive && <ChevronRight className="w-3.5 h-3.5 text-[#e25b38]" />}
              </div>
            </Link>
          );
        })}
      </nav>

      {/* Target Bounding Frame Footer */}
      <div className="p-4 border-t border-[#1e2638] bg-[#0a0d14]/70">
        <div className="text-[10px] font-mono text-slate-500 uppercase tracking-wider">Active Study Area</div>
        <div className="text-xs font-semibold text-slate-300 mt-0.5 truncate">Gale Crater / Mt Sharp</div>
        <div className="text-[10px] font-mono text-slate-500 mt-1 flex justify-between">
          <span>CRS: IAU2000</span>
          <span className="text-emerald-400">ONLINE</span>
        </div>
      </div>
    </aside>
  );
}

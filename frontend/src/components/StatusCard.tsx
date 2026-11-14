import React from "react";

interface StatusCardProps {
  label: string;
  value: string | number;
  subValue?: string;
  unit?: string;
  icon: React.ElementType;
  badge?: string;
}

export function StatusCard({ label, value, subValue, unit, icon: Icon, badge }: StatusCardProps) {
  return (
    <div className="bg-[#121622] border border-[#1e2638] rounded-xl p-4 flex flex-col justify-between hover:border-[#2b374e] transition-colors">
      <div className="flex items-center justify-between text-slate-400 mb-2">
        <span className="text-[11px] font-mono uppercase tracking-wider text-slate-400">{label}</span>
        <div className="w-7 h-7 rounded-lg bg-[#181e2e] flex items-center justify-center text-[#e25b38]">
          <Icon className="w-3.5 h-3.5" />
        </div>
      </div>
      <div className="flex items-baseline gap-1.5 mt-1">
        <span className="text-xl font-bold font-mono text-slate-100">{value}</span>
        {unit && <span className="text-xs font-mono text-slate-400">{unit}</span>}
      </div>
      {(subValue || badge) && (
        <div className="flex items-center justify-between mt-2 pt-2 border-t border-[#1a2130] text-[11px] text-slate-500">
          {subValue && <span>{subValue}</span>}
          {badge && (
            <span className="px-1.5 py-0.5 rounded text-[9px] font-mono bg-emerald-500/10 text-emerald-400 border border-emerald-500/20">
              {badge}
            </span>
          )}
        </div>
      )}
    </div>
  );
}

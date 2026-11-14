import React from "react";
import { Info, AlertCircle } from "lucide-react";

interface EmptyStateProps {
  title?: string;
  message?: string;
  actionLabel?: string;
  onAction?: () => void;
  icon?: React.ElementType;
}

export function EmptyState({
  title = "Scientific Data Not Yet Integrated",
  message = "This subsystem interface is scaffolded and ready for subsequent feature implementation prompts. In accordance with MARSCOPE scientific integrity principles, no synthetic data is displayed.",
  actionLabel,
  onAction,
  icon: Icon = Info,
}: EmptyStateProps) {
  return (
    <div className="rounded-xl border border-dashed border-[#252f44] bg-[#0e121c]/60 p-10 flex flex-col items-center justify-center text-center">
      <div className="w-12 h-12 rounded-full bg-[#161c2b] border border-[#252f44] flex items-center justify-center text-[#e25b38] mb-4 shadow-[0_0_20px_rgba(226,91,56,0.1)]">
        <Icon className="w-6 h-6" />
      </div>
      <h3 className="text-base font-semibold text-slate-200 mb-1">{title}</h3>
      <p className="text-xs text-slate-400 max-w-md leading-relaxed mb-4">{message}</p>
      {actionLabel && onAction && (
        <button
          onClick={onAction}
          className="px-4 py-2 rounded-lg bg-[#e25b38] hover:bg-[#f16f4d] text-white text-xs font-semibold tracking-wide transition-all shadow-[0_0_15px_rgba(226,91,56,0.3)]"
        >
          {actionLabel}
        </button>
      )}
      <div className="flex items-center gap-2 mt-4 text-[10px] font-mono text-slate-500 uppercase tracking-widest">
        <AlertCircle className="w-3.5 h-3.5 text-amber-500/80" />
        <span>Authentic NASA / PDS Data Pipeline Ready</span>
      </div>
    </div>
  );
}

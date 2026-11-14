import React from "react";

interface PageHeaderProps {
  title: string;
  badge?: string;
  description: string;
  actions?: React.ReactNode;
}

export function PageHeader({ title, badge, description, actions }: PageHeaderProps) {
  return (
    <div className="flex flex-col md:flex-row md:items-center justify-between pb-6 mb-6 border-b border-[#1e2638] gap-4">
      <div>
        <div className="flex items-center gap-3">
          <h1 className="text-2xl font-bold tracking-tight text-slate-100">{title}</h1>
          {badge && (
            <span className="px-2 py-0.5 rounded text-[10px] font-mono font-semibold uppercase bg-[#e25b38]/20 text-[#f16f4d] border border-[#e25b38]/30">
              {badge}
            </span>
          )}
        </div>
        <p className="text-xs text-slate-400 mt-1 max-w-2xl">{description}</p>
      </div>
      {actions && <div className="flex items-center gap-3">{actions}</div>}
    </div>
  );
}

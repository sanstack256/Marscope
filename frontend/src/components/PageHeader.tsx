import React from "react";

interface PageHeaderProps {
  title: string;
  badge?: string;
  description: string;
  actions?: React.ReactNode;
}

export function PageHeader({ title, badge, description, actions }: PageHeaderProps) {
  return (
    <div className="flex flex-col md:flex-row md:items-center justify-between pb-5 mb-5 border-b border-[var(--border-subtle)] gap-3">
      <div>
        <div className="flex items-center gap-2.5 flex-wrap">
          <h1 className="text-xl font-bold tracking-tight text-[var(--text-primary)]">{title}</h1>
          {badge && (
            <span className="px-2 py-0.5 rounded-[4px] text-[10px] font-mono font-semibold uppercase bg-[var(--accent-mars)]/15 text-[var(--accent-mars-hover)] border border-[var(--accent-mars)]/35">
              {badge}
            </span>
          )}
        </div>
        <p className="text-xs text-[var(--text-secondary)] mt-1 max-w-2xl leading-relaxed">{description}</p>
      </div>
      {actions && <div className="flex items-center gap-2.5 flex-wrap">{actions}</div>}
    </div>
  );
}

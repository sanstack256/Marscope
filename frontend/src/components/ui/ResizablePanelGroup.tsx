"use client";

import React, { useEffect, useRef, useState } from "react";

interface ResizablePanelGroupProps {
  leftPanel?: React.ReactNode;
  rightPanel?: React.ReactNode;
  centerPanel: React.ReactNode;
  storageKey?: string;
  defaultLeftWidth?: number;
  defaultRightWidth?: number;
  minSideWidth?: number;
  maxSideWidth?: number;
  leftCollapsed?: boolean;
  rightCollapsed?: boolean;
}

export function ResizablePanelGroup({
  leftPanel,
  rightPanel,
  centerPanel,
  storageKey = "marscope.panels",
  defaultLeftWidth = 280,
  defaultRightWidth = 320,
  minSideWidth = 220,
  maxSideWidth = 460,
  leftCollapsed = false,
  rightCollapsed = false,
}: ResizablePanelGroupProps) {
  const [leftWidth, setLeftWidth] = useState<number>(defaultLeftWidth);
  const [rightWidth, setRightWidth] = useState<number>(defaultRightWidth);
  const draggingRef = useRef<"left" | "right" | null>(null);

  useEffect(() => {
    const raf = window.requestAnimationFrame(() => {
      try {
        const raw = window.localStorage.getItem(storageKey);
        if (raw) {
          const parsed = JSON.parse(raw);
          if (typeof parsed.left === "number") setLeftWidth(parsed.left);
          if (typeof parsed.right === "number") setRightWidth(parsed.right);
        }
      } catch {
        // ignore storage access issues
      }
    });
    return () => window.cancelAnimationFrame(raf);
  }, [storageKey]);

  useEffect(() => {
    const onMove = (e: MouseEvent) => {
      if (!draggingRef.current) return;
      if (draggingRef.current === "left") {
        setLeftWidth((prev) => {
          const next = Math.min(maxSideWidth, Math.max(minSideWidth, prev + e.movementX));
          return next;
        });
      } else {
        setRightWidth((prev) => {
          const next = Math.min(maxSideWidth, Math.max(minSideWidth, prev - e.movementX));
          return next;
        });
      }
    };
    const onUp = () => {
      if (draggingRef.current) {
        draggingRef.current = null;
        try {
          window.localStorage.setItem(storageKey, JSON.stringify({ left: leftWidth, right: rightWidth }));
        } catch {
          // ignore
        }
      }
    };
    window.addEventListener("mousemove", onMove);
    window.addEventListener("mouseup", onUp);
    return () => {
      window.removeEventListener("mousemove", onMove);
      window.removeEventListener("mouseup", onUp);
    };
  }, [leftWidth, rightWidth, minSideWidth, maxSideWidth, storageKey]);

  return (
    <div className="flex flex-col lg:flex-row w-full gap-3 min-h-[520px]">
      {leftPanel && !leftCollapsed && (
        <>
          <aside
            className="w-full lg:shrink-0 ms-panel overflow-y-auto"
            style={{ ["--panel-w" as string]: `${leftWidth}px`, width: undefined }}
          >
            <div className="lg:w-[var(--panel-w)] h-full">{leftPanel}</div>
          </aside>
          <div
            role="separator"
            aria-orientation="vertical"
            aria-label="Resize left inspector panel"
            onMouseDown={() => {
              draggingRef.current = "left";
            }}
            className="hidden lg:block w-1 cursor-col-resize rounded hover:bg-[var(--accent-telemetry)]/50 transition-colors"
          />
        </>
      )}

      <div className="flex-1 min-w-0 flex flex-col">{centerPanel}</div>

      {rightPanel && !rightCollapsed && (
        <>
          <div
            role="separator"
            aria-orientation="vertical"
            aria-label="Resize right inspector panel"
            onMouseDown={() => {
              draggingRef.current = "right";
            }}
            className="hidden lg:block w-1 cursor-col-resize rounded hover:bg-[var(--accent-telemetry)]/50 transition-colors"
          />
          <aside
            className="w-full lg:shrink-0 ms-panel overflow-y-auto"
            style={{ ["--panel-w" as string]: `${rightWidth}px` }}
          >
            <div className="lg:w-[var(--panel-w)] h-full">{rightPanel}</div>
          </aside>
        </>
      )}
    </div>
  );
}

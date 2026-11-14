import { create } from "zustand";
import { PlanningMode, ScienceTarget } from "../types";

interface MissionStoreState {
  planningMode: PlanningMode;
  maxDurationHours: number;
  safetyReserveFactor: number;
  maxSlopeLimitDeg: number;
  selectedTargets: ScienceTarget[];
  setPlanningMode: (mode: PlanningMode) => void;
  setDuration: (hours: number) => void;
  setSafetyReserve: (factor: number) => void;
  addTarget: (target: ScienceTarget) => void;
  removeTarget: (targetId: string) => void;
  clearTargets: () => void;
}

export const useMissionStore = create<MissionStoreState>((set) => ({
  planningMode: "balanced",
  maxDurationHours: 6.0,
  safetyReserveFactor: 1.5,
  maxSlopeLimitDeg: 25.0,
  selectedTargets: [],
  setPlanningMode: (mode) => set({ planningMode: mode }),
  setDuration: (hours) => set({ maxDurationHours: hours }),
  setSafetyReserve: (factor) => set({ safetyReserveFactor: factor }),
  addTarget: (target) =>
    set((state) => ({
      selectedTargets: state.selectedTargets.some((t) => t.id === target.id)
        ? state.selectedTargets
        : [...state.selectedTargets, target],
    })),
  removeTarget: (targetId) =>
    set((state) => ({
      selectedTargets: state.selectedTargets.filter((t) => t.id !== targetId),
    })),
  clearTargets: () => set({ selectedTargets: [] }),
}));

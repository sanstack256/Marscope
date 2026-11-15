"use client";

import React, { useEffect, useState } from "react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { ArrowLeft, Compass, Eye, EyeOff, UserPlus } from "lucide-react";
import { useAuthMissionStore } from "../../stores/useAuthMissionStore";

export default function RegisterPage() {
  const router = useRouter();
  const { authenticated, astronaut, authError, register } = useAuthMissionStore();

  const [displayName, setDisplayName] = useState("");
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [showPassword, setShowPassword] = useState(false);
  const [busy, setBusy] = useState(false);
  const [localError, setLocalError] = useState<string | null>(null);

  useEffect(() => {
    if (authenticated && astronaut) {
      router.replace("/mission-control");
    }
  }, [authenticated, astronaut, router]);

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setLocalError(null);
    if (displayName.trim().length < 2) {
      setLocalError("Display name must be at least 2 characters.");
      return;
    }
    if (password.length < 10) {
      setLocalError("Password must be at least 10 characters with upper, lower, and numeric characters.");
      return;
    }
    setBusy(true);
    try {
      const ok = await register(email.trim(), password, displayName.trim());
      if (ok) {
        router.replace("/mission-control");
      }
    } finally {
      setBusy(false);
    }
  };

  return (
    <div className="min-h-screen bg-[#050505] text-white flex flex-col">
      <header className="border-b border-[#242424] bg-[#050505]">
        <div className="max-w-5xl mx-auto px-4 sm:px-6 h-16 flex items-center justify-between">
          <Link href="/" className="flex items-center gap-3">
            <div className="w-8 h-8 rounded-[6px] bg-[#FF6A1A]/15 border border-[#FF6A1A]/50 flex items-center justify-center">
              <Compass className="w-4 h-4 text-[#FF6A1A]" />
            </div>
            <div>
              <div className="text-sm font-bold tracking-[0.14em] leading-none">MARSCOPE</div>
              <div className="text-[10px] font-mono tracking-[0.14em] text-[#A1A1AA] mt-1">
                MARTIAN SURFACE INTELLIGENCE
              </div>
            </div>
          </Link>
          <Link href="/" className="inline-flex items-center gap-1.5 text-xs text-[#A1A1AA] hover:text-white">
            <ArrowLeft className="w-3.5 h-3.5" />
            <span>Back to Landing</span>
          </Link>
        </div>
      </header>

      <main className="flex-1 flex items-center justify-center px-4 py-12">
        <section className="w-full max-w-md rounded-[8px] border border-[#242424] bg-[#0B0B0B] p-6 sm:p-8 space-y-6">
          <div className="space-y-1.5">
            <div className="text-[11px] font-mono uppercase tracking-[0.16em] text-[#FF6A1A]">
              NEW OPERATOR ONBOARDING
            </div>
            <h1 className="text-2xl font-bold tracking-tight text-white">Create Astronaut Account</h1>
            <p className="text-xs text-[#A1A1AA]">
              Register a dedicated production account to create or join isolated Mars exploration missions.
            </p>
          </div>

          <form onSubmit={handleSubmit} className="space-y-4 text-xs">
            <div>
              <label htmlFor="reg-name" className="block text-[#A1A1AA] mb-1.5 font-medium">
                Astronaut Display Name
              </label>
              <input
                id="reg-name"
                type="text"
                required
                minLength={2}
                value={displayName}
                onChange={(e) => setDisplayName(e.target.value)}
                placeholder="Cmdr. Elena Vance"
                className="w-full px-3 py-2.5 rounded-[4px] bg-[#050505] border border-[#242424] focus:border-[#FF6A1A] outline-none text-white"
              />
            </div>

            <div>
              <label htmlFor="reg-email" className="block text-[#A1A1AA] mb-1.5 font-medium">
                Email Address
              </label>
              <input
                id="reg-email"
                type="email"
                required
                autoComplete="email"
                value={email}
                onChange={(e) => setEmail(e.target.value)}
                placeholder="astronaut@agency.org"
                className="w-full px-3 py-2.5 rounded-[4px] bg-[#050505] border border-[#242424] focus:border-[#FF6A1A] outline-none text-white"
              />
            </div>

            <div>
              <label htmlFor="reg-password" className="block text-[#A1A1AA] mb-1.5 font-medium">
                Password (10+ chars, upper + lower + digit)
              </label>
              <div className="relative">
                <input
                  id="reg-password"
                  type={showPassword ? "text" : "password"}
                  required
                  minLength={10}
                  autoComplete="new-password"
                  value={password}
                  onChange={(e) => setPassword(e.target.value)}
                  placeholder="Minimum 10 characters"
                  className="w-full px-3 py-2.5 pr-10 rounded-[4px] bg-[#050505] border border-[#242424] focus:border-[#FF6A1A] outline-none text-white"
                />
                <button
                  type="button"
                  onClick={() => setShowPassword((v) => !v)}
                  aria-label={showPassword ? "Hide password" : "Show password"}
                  className="absolute right-2.5 top-1/2 -translate-y-1/2 text-[#A1A1AA] hover:text-white"
                >
                  {showPassword ? <EyeOff className="w-4 h-4" /> : <Eye className="w-4 h-4" />}
                </button>
              </div>
            </div>

            {(localError || authError) && (
              <div
                role="alert"
                className="px-3 py-2 rounded-[4px] border border-[#DC3545]/50 bg-[#DC3545]/10 text-[#ff8590] text-xs"
              >
                {localError || authError}
              </div>
            )}

            <button
              type="submit"
              disabled={busy}
              className="w-full inline-flex items-center justify-center gap-2 px-4 py-2.5 rounded-[4px] bg-[#FF6A1A] hover:bg-[#FF7F32] text-white font-semibold tracking-wide transition-colors disabled:opacity-60"
            >
              <UserPlus className="w-4 h-4" />
              <span>{busy ? "Creating Account..." : "Register Astronaut"}</span>
            </button>
          </form>

          <div className="pt-4 border-t border-[#242424] flex flex-col sm:flex-row sm:items-center sm:justify-between gap-2 text-xs text-[#A1A1AA]">
            <Link href="/login" className="hover:text-white">
              Already registered? Sign In →
            </Link>
            <Link href="/login?demo=1" className="text-[#FF6A1A] hover:text-[#FF7F32] font-semibold">
              Try Judge Demo →
            </Link>
          </div>
        </section>
      </main>
    </div>
  );
}


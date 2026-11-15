"use client";

import React, { Suspense, useEffect, useState } from "react";
import Link from "next/link";
import { useRouter, useSearchParams } from "next/navigation";
import { ArrowLeft, Check, Compass, Copy, Eye, EyeOff, KeyRound, LogIn, ShieldAlert } from "lucide-react";
import { apiFetch } from "../../lib/constants";
import { DemoCredentialsConfig } from "../../types";
import { useAuthMissionStore } from "../../stores/useAuthMissionStore";

function sanitizeNextPath(raw: string | null): string {
  if (!raw || !raw.startsWith("/") || raw.startsWith("//") || raw.startsWith("/login") || raw.startsWith("/register")) {
    return "/mission-control";
  }
  return raw;
}

function LoginPageContent() {
  const router = useRouter();
  const searchParams = useSearchParams();
  const safeNext = sanitizeNextPath(searchParams.get("next"));
  const highlightDemo = searchParams.get("demo") === "1";

  const { authenticated, astronaut, authError, login } = useAuthMissionStore();

  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [showPassword, setShowPassword] = useState(false);
  const [busy, setBusy] = useState(false);
  const [localError, setLocalError] = useState<string | null>(null);

  // Forgot password mode
  const [resetMode, setResetMode] = useState(false);
  const [resetToken, setResetToken] = useState("");
  const [newPassword, setNewPassword] = useState("");
  const [resetNotice, setResetNotice] = useState<string | null>(null);

  // Judge Demo Config fetched from backend
  const [demoConfig, setDemoConfig] = useState<DemoCredentialsConfig | null>(null);
  const [demoLoading, setDemoLoading] = useState(true);
  const [demoBusy, setDemoBusy] = useState(false);
  const [copiedField, setCopiedField] = useState<"email" | "password" | null>(null);

  useEffect(() => {
    if (authenticated && astronaut) {
      router.replace(astronaut.is_demo ? "/mission-control" : safeNext);
    }
  }, [authenticated, astronaut, router, safeNext]);

  useEffect(() => {
    let active = true;
    (async () => {
      try {
        const res = await apiFetch("/demo/config");
        if (res.ok && active) {
          setDemoConfig(await res.json());
        }
      } catch {
        // leave null
      } finally {
        if (active) setDemoLoading(false);
      }
    })();
    return () => {
      active = false;
    };
  }, []);

  const handleSignIn = async (e: React.FormEvent) => {
    e.preventDefault();
    setLocalError(null);
    if (!email.trim() || !password) {
      setLocalError("Enter your astronaut email and password.");
      return;
    }
    setBusy(true);
    try {
      const ok = await login(email.trim(), password);
      if (ok) {
        const currentAstro = useAuthMissionStore.getState().astronaut;
        router.replace(currentAstro?.is_demo ? "/mission-control" : safeNext);
      }
    } finally {
      setBusy(false);
    }
  };

  const handleEnterDemo = async () => {
    if (!demoConfig?.enabled || !demoConfig.email || !demoConfig.password) return;
    setDemoBusy(true);
    setLocalError(null);
    try {
      const ok = await login(demoConfig.email, demoConfig.password);
      if (ok) {
        router.replace("/mission-control");
      }
    } finally {
      setDemoBusy(false);
    }
  };

  const handleCopy = async (field: "email" | "password", val: string) => {
    try {
      await navigator.clipboard.writeText(val);
      setCopiedField(field);
      setTimeout(() => setCopiedField(null), 1800);
    } catch {
      // ignore clipboard restrictions
    }
  };

  const handleResetRequest = async () => {
    setResetNotice(null);
    if (!email.trim()) {
      setResetNotice("Enter your astronaut email first.");
      return;
    }
    const res = await apiFetch("/auth/password-reset/request", {
      method: "POST",
      body: JSON.stringify({ email: email.trim() }),
    });
    const body = await res.json().catch(() => ({}));
    setResetNotice(
      body.reset_token_preview
        ? `Reset token (dev/test): ${body.reset_token_preview}`
        : body.message || "If an active astronaut account exists, a reset token has been issued."
    );
  };

  const handleResetConfirm = async (e: React.FormEvent) => {
    e.preventDefault();
    setResetNotice(null);
    const res = await apiFetch("/auth/password-reset/confirm", {
      method: "POST",
      body: JSON.stringify({ token: resetToken.trim(), new_password: newPassword }),
    });
    if (res.ok) {
      setResetNotice("Password updated. Sign in with your new credentials.");
      setResetMode(false);
      setResetToken("");
      setNewPassword("");
    } else {
      const b = await res.json().catch(() => ({}));
      setResetNotice(b.detail || "Failed to confirm reset token.");
    }
  };

  return (
    <div className="min-h-screen bg-[#050505] text-white flex flex-col">
      <header className="border-b border-[#242424] bg-[#050505]">
        <div className="max-w-6xl mx-auto px-4 sm:px-6 h-16 flex items-center justify-between">
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

      <main className="flex-1 max-w-6xl w-full mx-auto px-4 sm:px-6 py-10 sm:py-16 grid grid-cols-1 lg:grid-cols-12 gap-8 items-start">
        {/* Left: Normal Astronaut Sign-In */}
        <section className="lg:col-span-6 rounded-[8px] border border-[#242424] bg-[#0B0B0B] p-6 sm:p-8 space-y-6">
          <div className="space-y-1.5">
            <div className="text-[11px] font-mono uppercase tracking-[0.16em] text-[#FF6A1A]">
              ASTRONAUT AUTHENTICATION
            </div>
            <h1 className="text-2xl font-bold tracking-tight text-white">
              {resetMode ? "Reset Astronaut Password" : "Sign In to MARSCOPE"}
            </h1>
            <p className="text-xs text-[#A1A1AA]">
              Access your isolated multi-astronaut missions, field observations, and EVA operations.
            </p>
          </div>

          {!resetMode ? (
            <form onSubmit={handleSignIn} className="space-y-4 text-xs">
              <div>
                <label htmlFor="login-email" className="block text-[#A1A1AA] mb-1.5 font-medium">
                  Astronaut Email
                </label>
                <input
                  id="login-email"
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
                <div className="flex items-center justify-between mb-1.5">
                  <label htmlFor="login-password" className="text-[#A1A1AA] font-medium">
                    Password
                  </label>
                  <button
                    type="button"
                    onClick={() => {
                      setResetMode(true);
                      setResetNotice(null);
                    }}
                    className="text-[11px] text-[#A1A1AA] hover:text-[#FF6A1A]"
                  >
                    Forgot password?
                  </button>
                </div>
                <div className="relative">
                  <input
                    id="login-password"
                    type={showPassword ? "text" : "password"}
                    required
                    autoComplete="current-password"
                    value={password}
                    onChange={(e) => setPassword(e.target.value)}
                    placeholder="Enter password"
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
                <LogIn className="w-4 h-4" />
                <span>{busy ? "Signing In..." : "Sign In"}</span>
              </button>
            </form>
          ) : (
            <form onSubmit={handleResetConfirm} className="space-y-4 text-xs">
              <div>
                <label className="block text-[#A1A1AA] mb-1.5">Astronaut Email</label>
                <div className="flex gap-2">
                  <input
                    type="email"
                    required
                    value={email}
                    onChange={(e) => setEmail(e.target.value)}
                    placeholder="astronaut@agency.org"
                    className="flex-1 px-3 py-2 rounded-[4px] bg-[#050505] border border-[#242424] focus:border-[#FF6A1A] outline-none text-white"
                  />
                  <button
                    type="button"
                    onClick={() => void handleResetRequest()}
                    className="px-3 py-2 rounded-[4px] border border-[#242424] bg-[#111111] hover:border-white text-white"
                  >
                    Request Token
                  </button>
                </div>
              </div>
              <div>
                <label className="block text-[#A1A1AA] mb-1.5">Reset Token</label>
                <input
                  type="text"
                  required
                  value={resetToken}
                  onChange={(e) => setResetToken(e.target.value)}
                  className="w-full px-3 py-2 rounded-[4px] bg-[#050505] border border-[#242424] font-mono text-white"
                />
              </div>
              <div>
                <label className="block text-[#A1A1AA] mb-1.5">New Password (10+ chars)</label>
                <input
                  type="password"
                  required
                  minLength={10}
                  value={newPassword}
                  onChange={(e) => setNewPassword(e.target.value)}
                  className="w-full px-3 py-2 rounded-[4px] bg-[#050505] border border-[#242424] text-white"
                />
              </div>
              {resetNotice && (
                <div className="px-3 py-2 rounded-[4px] border border-[#242424] bg-[#111111] text-[#E4E4E7] font-mono text-[11px]">
                  {resetNotice}
                </div>
              )}
              <div className="flex gap-2">
                <button
                  type="submit"
                  className="flex-1 inline-flex items-center justify-center gap-1.5 px-4 py-2.5 rounded-[4px] bg-[#FF6A1A] hover:bg-[#FF7F32] text-white font-semibold"
                >
                  <KeyRound className="w-3.5 h-3.5" />
                  <span>Confirm Reset</span>
                </button>
                <button
                  type="button"
                  onClick={() => setResetMode(false)}
                  className="px-4 py-2.5 rounded-[4px] border border-[#242424] text-[#A1A1AA] hover:text-white"
                >
                  Cancel
                </button>
              </div>
            </form>
          )}

          <div className="pt-4 border-t border-[#242424] flex items-center justify-between text-xs text-[#A1A1AA]">
            <span>New astronaut operator?</span>
            <Link href="/register" className="text-[#FF6A1A] hover:text-[#FF7F32] font-semibold">
              Create Astronaut Account →
            </Link>
          </div>
        </section>

        {/* Right: Distinct JUDGE DEMO ACCESS Panel */}
        <section
          className={`lg:col-span-6 rounded-[8px] border bg-[#111111] p-6 sm:p-8 space-y-5 ${
            highlightDemo ? "border-[#FF6A1A]" : "border-[#242424]"
          }`}
        >
          <div className="flex items-center justify-between gap-2">
            <div className="text-[11px] font-mono uppercase tracking-[0.16em] text-[#FF6A1A] font-bold">
              JUDGE DEMO ACCESS
            </div>
            <span className="px-2 py-0.5 rounded-[4px] bg-[#FF6A1A]/15 border border-[#FF6A1A]/50 text-[#FF6A1A] font-mono text-[10px] font-bold">
              DEMO SANDBOX
            </span>
          </div>

          <div className="space-y-1.5">
            <h2 className="text-xl font-bold text-white">Explore the Prepared Gale Crater Mission</h2>
            <p className="text-xs text-[#A1A1AA] leading-relaxed">
              Enter the isolated demonstration mission immediately with three seeded demo astronauts, an active
              SOS from DEMO ASTRONAUT ALPHA, and field observations from Alpha and Bravo.
            </p>
          </div>

          {demoLoading ? (
            <div className="p-4 rounded-[6px] border border-[#242424] bg-[#0B0B0B] text-xs font-mono text-[#A1A1AA]">
              Loading provisioned demo credentials...
            </div>
          ) : demoConfig?.enabled && demoConfig.email && demoConfig.password ? (
            <div className="space-y-4">
              <div className="rounded-[6px] border border-[#242424] bg-[#050505] p-4 space-y-3 text-xs">
                <div className="flex items-center justify-between gap-3">
                  <div className="min-w-0">
                    <div className="text-[10px] font-mono uppercase text-[#71717A]">Demo Username / Email</div>
                    <div className="font-mono text-white truncate mt-0.5">{demoConfig.email}</div>
                  </div>
                  <button
                    type="button"
                    onClick={() => void handleCopy("email", demoConfig.email!)}
                    className="inline-flex items-center gap-1.5 px-2.5 py-1.5 rounded-[4px] border border-[#242424] hover:border-[#FF6A1A] text-[#A1A1AA] hover:text-white shrink-0"
                  >
                    {copiedField === "email" ? <Check className="w-3.5 h-3.5 text-[#1F9D68]" /> : <Copy className="w-3.5 h-3.5" />}
                    <span>{copiedField === "email" ? "Copied" : "Copy username"}</span>
                  </button>
                </div>

                <div className="pt-2.5 border-t border-[#242424] flex items-center justify-between gap-3">
                  <div className="min-w-0">
                    <div className="text-[10px] font-mono uppercase text-[#71717A]">Demo Password</div>
                    <div className="font-mono text-white truncate mt-0.5">{demoConfig.password}</div>
                  </div>
                  <button
                    type="button"
                    onClick={() => void handleCopy("password", demoConfig.password!)}
                    className="inline-flex items-center gap-1.5 px-2.5 py-1.5 rounded-[4px] border border-[#242424] hover:border-[#FF6A1A] text-[#A1A1AA] hover:text-white shrink-0"
                  >
                    {copiedField === "password" ? <Check className="w-3.5 h-3.5 text-[#1F9D68]" /> : <Copy className="w-3.5 h-3.5" />}
                    <span>{copiedField === "password" ? "Copied" : "Copy password"}</span>
                  </button>
                </div>
              </div>

              <button
                type="button"
                onClick={() => void handleEnterDemo()}
                disabled={demoBusy}
                className="w-full py-3 rounded-[4px] bg-[#FF6A1A] hover:bg-[#FF7F32] text-white text-xs sm:text-sm font-semibold tracking-wider transition-colors disabled:opacity-60"
              >
                {demoBusy ? "ENTERING DEMO MISSION..." : "ENTER DEMO"}
              </button>

              <div className="flex items-start gap-2 text-[11px] text-[#A1A1AA] leading-relaxed">
                <ShieldAlert className="w-4 h-4 text-[#FF6A1A] shrink-0 mt-0.5" />
                <span>{demoConfig.disclaimer}</span>
              </div>
            </div>
          ) : (
            <div className="p-4 rounded-[6px] border border-[#242424] bg-[#0B0B0B] text-xs text-[#A1A1AA]">
              Judge demo access is disabled on this server instance.
            </div>
          )}
        </section>
      </main>
    </div>
  );
}

export default function LoginPage() {
  return (
    <Suspense
      fallback={
        <div className="min-h-screen bg-[#050505] text-[#A1A1AA] flex items-center justify-center text-xs font-mono">
          Loading sign-in portal...
        </div>
      }
    >
      <LoginPageContent />
    </Suspense>
  );
}


import type { NextConfig } from "next";
import path from "path";

const backendInternalUrl = process.env.BACKEND_INTERNAL_URL?.trim().replace(/\/+$/, "");
const isVercel = process.env.VERCEL === "1" || process.env.VERCEL === "true";

const nextConfig: NextConfig = {
  outputFileTracingRoot: path.join(__dirname, "../"),
  reactStrictMode: true,
  async rewrites() {
    if (backendInternalUrl) {
      return [
        {
          source: "/api/:path*",
          destination: `${backendInternalUrl}/api/:path*`,
        },
      ];
    }
    if (!isVercel) {
      return [
        {
          source: "/api/:path*",
          destination: "http://127.0.0.1:8000/api/:path*",
        },
      ];
    }
    return [];
  },
};

export default nextConfig;

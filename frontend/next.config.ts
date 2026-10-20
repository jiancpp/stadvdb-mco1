import type { NextConfig } from "next";

const BACKEND ="https://years-coupons-fastest-trackbacks.trycloudflare.com"
  // process.env.BACKEND_URL ??
  // // "https://institutions-somewhere-composed-isp.trycloudflare.com"; 
  // "http://127.0.0.1:8000";

const nextConfig: NextConfig = {
  // Allow Cloudflare Tunnel domains for Next.js HMR & dev resources
  allowedDevOrigins: ["*.trycloudflare.com"],

  // Proxy /api/* to FastAPI so the browser needs no CORS setup.
  async rewrites() {
    return [{ source: "/api/:path*", destination: `${BACKEND}/api/:path*` }];
  },
};

export default nextConfig;
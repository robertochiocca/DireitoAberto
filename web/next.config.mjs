/** @type {import('next').NextConfig} */
const API_URL = process.env.API_URL ?? "http://localhost:8000";

const nextConfig = {
  async rewrites() {
    // O navegador chama /api/... no próprio Next; o Next repassa ao FastAPI.
    return [{ source: "/api/:path*", destination: `${API_URL}/api/:path*` }];
  },
};

export default nextConfig;

import type { NextConfig } from "next";

const nextConfig: NextConfig = {
  // Backend API is on a separate port; CORS is already allowed on the backend.
  // Set NEXT_PUBLIC_API_URL in .env.local to point to your backend.
};

export default nextConfig;

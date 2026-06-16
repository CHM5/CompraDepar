import type { NextConfig } from "next";

// En GitHub Pages el repo se sirve desde /CompraDepar.
// Localmente no hay basePath para que localhost:3000 siga funcionando.
const nextConfig: NextConfig = {
  output: "export",
  images: { unoptimized: true },
};


export default nextConfig;

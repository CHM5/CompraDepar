import type { NextConfig } from "next";

// En GitHub Pages el repo se sirve desde /CompraDepar.
// Localmente no hay basePath para que localhost:3000 siga funcionando.
const basePath = process.env.NEXT_PUBLIC_BASE_PATH ?? "";

const nextConfig: NextConfig = {
  output: "export",          // genera carpeta `out/` con HTML/CSS/JS estáticos
  basePath,                  // "" local | "/CompraDepar" en GitHub Pages
  images: { unoptimized: true }, // requerido para export estático
};

export default nextConfig;

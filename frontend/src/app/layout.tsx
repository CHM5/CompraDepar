import type { Metadata } from "next";
import { Inter } from "next/font/google";
import "./globals.css";
import { Providers } from "@/components/Providers";

const inter = Inter({ subsets: ["latin"] });

export const metadata: Metadata = {
  title: "Depar Finder — Departamentos en CABA",
  description:
    "Buscá departamentos en Capital Federal usando lenguaje natural. Resultados de Zonaprop, Argenprop, MEL y más.",
  icons: {
    icon: "/depar-finder-logo.svg",
  },
};

export default function RootLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  return (
    <html lang="es">
      <body className={`${inter.className} min-h-screen bg-neutral-50`}>
        <Providers>{children}</Providers>
      </body>
    </html>
  );
}

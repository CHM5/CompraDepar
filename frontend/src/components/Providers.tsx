"use client";

import { QueryClientProvider } from "@tanstack/react-query";
import { ReactQueryDevtools } from "@tanstack/react-query-devtools";
import { queryClient } from "@/lib/queryClient";

/**
 * Para activar Clerk:
 * 1. Agrega NEXT_PUBLIC_CLERK_PUBLISHABLE_KEY y CLERK_SECRET_KEY en .env.local
 * 2. Descomenta el import y el ClerkProvider de abajo.
 */
// import { ClerkProvider } from "@clerk/nextjs";

export function Providers({ children }: { children: React.ReactNode }) {
  return (
    <QueryClientProvider client={queryClient}>
      {children}
      <ReactQueryDevtools initialIsOpen={false} />
    </QueryClientProvider>
  );
}

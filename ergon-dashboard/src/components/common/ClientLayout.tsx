"use client";

/**
 * ClientLayout - Client-side layout wrapper.
 *
 * Includes components that need client-side functionality,
 * like the ConnectionStatus banner.
 */

import { ConnectionStatus } from "./ConnectionStatus";

interface ClientLayoutProps {
  children: React.ReactNode;
}

export function ClientLayout({ children }: ClientLayoutProps) {
  return (
    <>
      {children}
      <ConnectionStatus />
    </>
  );
}

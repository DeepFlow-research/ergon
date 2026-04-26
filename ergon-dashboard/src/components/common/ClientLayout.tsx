"use client";

import { BuildHealthToast } from "./BuildHealthToast";
import { ConnectionStatus } from "./ConnectionStatus";
import { Topbar } from "@/components/shell/Topbar";

interface ClientLayoutProps {
  children: React.ReactNode;
}

export function ClientLayout({ children }: ClientLayoutProps) {
  return (
    <div className="flex h-screen flex-col overflow-hidden">
      <Topbar />
      <div className="relative min-h-0 flex-1 overflow-auto">{children}</div>
      <ConnectionStatus />
      <BuildHealthToast />
    </div>
  );
}

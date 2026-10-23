import type { Metadata } from "next";
import "./globals.css";
export const metadata: Metadata = {
  title: {
    default: "FlowForge AI — Build with intent",
    template: "%s | FlowForge AI",
  },
  description:
    "Build AI agents, connect workflows, and keep every execution in view.",
};
export default function RootLayout({
  children,
}: Readonly<{ children: React.ReactNode }>) {
  return (
    <html lang="en">
      <body>{children}</body>
    </html>
  );
}

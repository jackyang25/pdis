import type { Metadata } from "next";
import { Inter, JetBrains_Mono } from "next/font/google";
import { AppShell } from "@/components/app-shell";
import "./globals.css";

// Inter Tight — slightly tighter than Inter, warmer feel for an agent surface.
// Falls back to system if Google fonts can't load.
const sans = Inter({
  subsets: ["latin"],
  variable: "--font-sans",
  display: "swap",
  weight: ["400", "500", "600", "700"],
});

const mono = JetBrains_Mono({
  subsets: ["latin"],
  variable: "--font-mono",
  display: "swap",
});

export const metadata: Metadata = {
  title: "PDIS",
  description: "Product Development Intelligence Suite",
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en" className={`${sans.variable} ${mono.variable}`}>
      <body className="min-h-screen bg-background font-sans">
        <AppShell>{children}</AppShell>
      </body>
    </html>
  );
}

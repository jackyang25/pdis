import type { Metadata } from "next";
import { JetBrains_Mono, Noto_Sans, Noto_Serif } from "next/font/google";
import { AppShell } from "@/components/app-shell";
import "@xyflow/react/dist/style.css";
import "./globals.css";

/**
 * The Gates Foundation's own two faces, read from `--font-sans` and `--font-serif` in their
 * published stylesheet. Replaces Inter and Inter Tight, which were well-chosen placeholders
 * with no relationship to the organisation whose work this reports on.
 *
 * Sans for everything, including headings, and not their serif. Their site sets body copy in
 * Noto Serif, which reads well at the sizes a marketing page uses and badly at the ones this
 * interface uses: most of a result is 10 and 11px, in tables and in dense rows. A serif there
 * costs legibility to gain identity, which is the wrong trade for a tool people read numbers
 * from.
 *
 * `Noto Stats`, their display face, is not public. Their own `--font-display` token falls back
 * to Noto Serif, so the serif below is used exactly where they use it: a page title, the
 * wordmark, nothing at a data size.
 */
const sans = Noto_Sans({
  subsets: ["latin"],
  variable: "--font-sans",
  display: "swap",
  weight: ["400", "500", "600", "700"],
});

const display = Noto_Serif({
  subsets: ["latin"],
  variable: "--font-display",
  display: "swap",
  weight: ["500", "600", "700"],
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

const themeScript = `
  try {
    const stored = localStorage.getItem("pdis-theme");
    const dark = stored === "dark";
    document.documentElement.classList.toggle("dark", dark);
    document.documentElement.style.colorScheme = dark ? "dark" : "light";
  } catch (_) {}
`;

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en" suppressHydrationWarning className={`${sans.variable} ${display.variable} ${mono.variable}`}>
      <head>
        <script dangerouslySetInnerHTML={{ __html: themeScript }} />
      </head>
      <body className="min-h-screen bg-background font-sans text-foreground">
        <AppShell>{children}</AppShell>
      </body>
    </html>
  );
}

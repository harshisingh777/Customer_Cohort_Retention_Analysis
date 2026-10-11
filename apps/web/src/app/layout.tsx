import type { Metadata, Viewport } from "next";
import { Public_Sans, Source_Serif_4 } from "next/font/google";
import "@/styles/globals.css";

// Self-hosted at build time by next/font; swap so text is never invisible.
const sans = Public_Sans({ subsets: ["latin"], variable: "--font-public-sans", display: "swap" });
const serif = Source_Serif_4({
  subsets: ["latin"],
  axes: ["opsz"],
  variable: "--font-source-serif",
  display: "swap",
});

export const metadata: Metadata = {
  title: { default: "Retention", template: "%s · Retention" },
  description: "Are the customers you acquire coming back, and which ones?",
  robots: { index: false, follow: false },
};

export const viewport: Viewport = { themeColor: "#EEF1F3", width: "device-width", initialScale: 1 };

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en" className={`${sans.variable} ${serif.variable}`}>
      <body>{children}</body>
    </html>
  );
}

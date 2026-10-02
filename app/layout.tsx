import type { Metadata } from "next";
import "./globals.css";

export const metadata: Metadata = {
  title: "Anatomy Evidence Lab",
  description: "Review anatomy lecture notes, inspect supporting evidence, and study faculty-approved material.",
  other: {
    "codex-preview": "development",
  },
  icons: {
    icon: "/favicon.svg",
    shortcut: "/favicon.svg",
  },
};

export default function RootLayout({
  children,
}: Readonly<{
  children: React.ReactNode;
}>) {
  return (
    <html lang="en">
      <body className="antialiased">{children}</body>
    </html>
  );
}

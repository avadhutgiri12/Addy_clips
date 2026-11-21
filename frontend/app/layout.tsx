import type { Metadata } from "next";
import "./globals.css";

export const metadata: Metadata = {
  title: "Addy Clips — Turn every stream into a highlight",
  description: "A local-first AI gaming video clipping studio.",
  applicationName: "Addy Clips",
};

export default function RootLayout({
  children,
}: Readonly<{ children: React.ReactNode }>) {
  return (
    <html lang="en" data-type="software">
      <body>{children}</body>
    </html>
  );
}

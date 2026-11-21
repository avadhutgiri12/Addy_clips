import type { Metadata } from "next";
import "./globals.css";

export const metadata: Metadata = {
  title: "Addy Clips — GTA VI clip studio",
  description: "Find, frame, and export your best GTA VI moments.",
};

export default function RootLayout({ children }: Readonly<{ children: React.ReactNode }>) {
  return <html lang="en"><body>{children}</body></html>;
}

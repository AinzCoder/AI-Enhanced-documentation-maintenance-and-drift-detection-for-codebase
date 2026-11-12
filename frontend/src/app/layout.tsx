
import type { Metadata } from "next";
import { Geist, Geist_Mono } from "next/font/google";
import "./globals.css";
import AppShell from "./components/layout/AppShell";
import { RepositoryAnalysisProvider } from "./components/repository/RepositoryAnalysisContext";

const geistSans = Geist({
  variable: "--font-geist-sans",
  subsets: ["latin"],
});

const geistMono = Geist_Mono({
  variable: "--font-geist-mono",
  subsets: ["latin"],
});

export const metadata: Metadata = {
  title: "DocGuard | AI Documentation Maintenance",
  description:
    "AI-powered documentation maintenance and drift detection for codebases.",
};

export default function RootLayout({
  children,
}: Readonly<{ children: React.ReactNode }>) {
  return (
    <html
      lang="en"
      className={`${geistSans.variable} ${geistMono.variable} h-full antialiased`}
    >
      <body className="min-h-full">
        <RepositoryAnalysisProvider>
          <AppShell>{children}</AppShell>
        </RepositoryAnalysisProvider>
      </body>
    </html>
  );
}

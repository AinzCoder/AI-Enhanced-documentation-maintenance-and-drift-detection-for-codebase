
import type { Metadata } from "next";
import { Geist, Geist_Mono } from "next/font/google";
import "./globals.css";
import AppShell from "./components/layout/AppShell";
import { RepositoryAnalysisProvider } from "./components/repository/RepositoryAnalysisContext";
import { getServerSession } from "next-auth";
import { authOptions } from "@/lib/auth";
import { isHosted } from "@/lib/deployment";
import AuthControls from "./components/layout/AuthControls";
import { Suspense } from "react";

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

async function HostedBoundary({ children }: Readonly<{ children: React.ReactNode }>) {
  const session = await getServerSession(authOptions());
  if (!session || !session.apiSessionValid) {
    return <main className="mx-auto max-w-xl p-8">
      <AuthControls expired={Boolean(session)} />
    </main>;
  }
  return <RepositoryAnalysisProvider>
    <AuthControls name={session.user?.name || session.user?.email || "User"} />
    <AppShell>{children}</AppShell>
  </RepositoryAnalysisProvider>;
}

export default function RootLayout({
  children,
}: Readonly<{ children: React.ReactNode }>) {
  return (
    <html
      lang="en"
      className={`${geistSans.variable} ${geistMono.variable} h-full antialiased`}
    >
      <body className="min-h-full">
        {isHosted ? (
          <Suspense fallback={<p role="status" className="p-8">Checking your session...</p>}>
            <HostedBoundary>{children}</HostedBoundary>
          </Suspense>
        ) : (
          <RepositoryAnalysisProvider>
            <AppShell>{children}</AppShell>
          </RepositoryAnalysisProvider>
        )}
      </body>
    </html>
  );
}

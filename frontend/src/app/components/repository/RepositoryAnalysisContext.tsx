"use client";

import { createContext, useContext, useState } from "react";
import type { ReactNode } from "react";

interface RepositoryAnalysisContextValue {
  repositoryPath: string;
  setRepositoryPath: (path: string) => void;
}

const RepositoryAnalysisContext =
  createContext<RepositoryAnalysisContextValue | null>(null);

export function RepositoryAnalysisProvider({
  children,
}: {
  children: ReactNode;
}) {
  const [repositoryPath, setRepositoryPath] = useState("");

  return (
    <RepositoryAnalysisContext.Provider
      value={{ repositoryPath, setRepositoryPath }}
    >
      {children}
    </RepositoryAnalysisContext.Provider>
  );
}

export function useRepositoryAnalysis() {
  const context = useContext(RepositoryAnalysisContext);
  if (!context) {
    throw new Error(
      "useRepositoryAnalysis must be used within RepositoryAnalysisProvider."
    );
  }
  return context;
}

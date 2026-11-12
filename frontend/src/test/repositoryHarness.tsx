"use client";

import { useEffect, type ReactNode } from "react";
import {
  RepositoryAnalysisProvider,
  useRepositoryAnalysis,
} from "../app/components/repository/RepositoryAnalysisContext";

function RepositoryValue({
  repositoryPath,
}: {
  repositoryPath: string;
}) {
  const { setRepositoryPath } = useRepositoryAnalysis();
  useEffect(() => {
    setRepositoryPath(repositoryPath);
  }, [repositoryPath, setRepositoryPath]);
  return null;
}

export function RepositoryHarness({
  repositoryPath,
  nextRepositoryPath,
  children,
}: {
  repositoryPath: string;
  nextRepositoryPath?: string;
  children: ReactNode;
}) {
  return (
    <RepositoryAnalysisProvider>
      <RepositoryValue repositoryPath={repositoryPath} />
      {nextRepositoryPath && (
        <RepositorySwitcher repositoryPath={nextRepositoryPath} />
      )}
      {children}
    </RepositoryAnalysisProvider>
  );
}

function RepositorySwitcher({ repositoryPath }: { repositoryPath: string }) {
  const { setRepositoryPath } = useRepositoryAnalysis();
  return (
    <button type="button" onClick={() => setRepositoryPath(repositoryPath)}>
      Switch repository
    </button>
  );
}

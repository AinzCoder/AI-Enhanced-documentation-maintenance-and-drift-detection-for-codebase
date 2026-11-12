const githubUrlPattern =
  /^https:\/\/github\.com\/([a-z0-9](?:[a-z0-9-]{0,37}[a-z0-9])?)\/([a-z0-9_.-]{1,100})\/?$/i;

export function isValidGithubRepositoryUrl(value: string): boolean {
  const match = githubUrlPattern.exec(value);
  if (!match || match[0] !== value || match[1].includes("--")) return false;
  const repository = match[2].replace(/\.git$/i, "");
  return repository.length > 0 && repository !== "." && repository !== ".." &&
    !repository.endsWith(".");
}

// Advisory UI limit until the upload service defines an authoritative limit.
export const MAX_ZIP_SIZE = 25 * 1024 * 1024;

export function validateZipFile(file: File): string | null {
  if (!file.name.toLowerCase().endsWith(".zip")) {
    return "Choose a file with a .zip extension.";
  }
  if (file.size === 0) return "The ZIP file is empty.";
  if (file.size > MAX_ZIP_SIZE) {
    return "The ZIP file must be 25 MiB or smaller.";
  }
  return null;
}

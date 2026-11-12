function canonicalWindowsPath(path: string): string | null {
  const normalizedSeparators = path.trim().replaceAll("/", "\\");
  const driveMatch = normalizedSeparators.match(/^([A-Za-z]:)\\(.*)$/);
  const uncMatch = normalizedSeparators.match(/^\\\\([^\\]+)\\([^\\]+)(.*)$/);
  let prefix: string;
  let rest: string;

  if (driveMatch) {
    prefix = driveMatch[1];
    rest = driveMatch[2];
  } else if (uncMatch) {
    prefix = `\\\\${uncMatch[1]}\\${uncMatch[2]}`;
    rest = uncMatch[3].replace(/^\\+/, "");
  } else {
    return null;
  }

  const parts: string[] = [];
  for (const part of rest.split("\\")) {
    if (!part || part === ".") {
      continue;
    }
    if (part === "..") {
      if (parts.length === 0) {
        return null;
      }
      parts.pop();
    } else {
      parts.push(part);
    }
  }
  return `${prefix}\\${parts.join("\\")}`.toLowerCase();
}

export async function getWindowsRepositoryIdentity(
  path: string
): Promise<string | null> {
  const canonicalPath = canonicalWindowsPath(path);
  if (!canonicalPath || !globalThis.crypto?.subtle) {
    return null;
  }
  const bytes = new TextEncoder().encode(canonicalPath);
  const digest = await crypto.subtle.digest("SHA-256", bytes);
  return Array.from(new Uint8Array(digest), (byte) =>
    byte.toString(16).padStart(2, "0")
  ).join("");
}

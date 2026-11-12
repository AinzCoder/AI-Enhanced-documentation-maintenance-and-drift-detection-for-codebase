import { isHosted } from "./deployment";

export function isValidRepositorySelection(value: string): boolean {
  if (isHosted) return /^[0-9a-f]{32}$/.test(value);
  return /^[A-Za-z]:[\\/]/.test(value) || /^\\\\[^\\]+\\[^\\]+/.test(value);
}

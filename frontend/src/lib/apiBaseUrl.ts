import { isHosted } from "./deployment";

export const apiBaseUrl = isHosted
  ? "/api/backend"
  : process.env.NEXT_PUBLIC_API_BASE_URL?.trim() || "http://127.0.0.1:8000";

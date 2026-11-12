import { NextRequest } from "next/server";
import { backendProxy } from "@/lib/backendProxy";

export function GET(request: NextRequest) {
  return backendProxy(request, "/");
}

import { NextRequest } from "next/server";
import { backendProxy } from "@/lib/backendProxy";

async function handler(request: NextRequest, context: { params: Promise<{ path: string[] }> }) {
  return backendProxy(request, `/${(await context.params).path.join("/")}`);
}

export { handler as GET, handler as POST };

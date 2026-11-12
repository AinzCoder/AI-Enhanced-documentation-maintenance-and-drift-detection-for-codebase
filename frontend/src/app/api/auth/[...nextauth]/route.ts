import NextAuth from "next-auth";
import { authOptions } from "@/lib/auth";
import { isHosted } from "@/lib/deployment";

async function handler(request: Request, context: { params: Promise<{ nextauth: string[] }> }) {
  if (!isHosted) return new Response("Not found", { status: 404 });
  return NextAuth(authOptions())(request, context);
}

export { handler as GET, handler as POST };

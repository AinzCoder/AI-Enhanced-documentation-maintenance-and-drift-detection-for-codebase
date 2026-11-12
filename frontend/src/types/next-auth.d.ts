import "next-auth";
import "next-auth/jwt";

declare module "next-auth" {
  interface Session {
    apiSessionValid?: boolean;
  }
}

declare module "next-auth/jwt" {
  interface JWT {
    apiAccessToken?: string;
    apiAccessTokenExpires?: number;
  }
}

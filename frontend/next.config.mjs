const isStaticExport = process.env.STATIC_EXPORT === "1";
const firebaseProjectId = process.env.NEXT_PUBLIC_FIREBASE_PROJECT_ID;
const firebaseAuthHelperOrigin = (
  process.env.FIREBASE_AUTH_HELPER_ORIGIN ||
  (firebaseProjectId ? `https://${firebaseProjectId}.firebaseapp.com` : null)
)
  ?.replace(/\/+$/, "");

/** @type {import('next').NextConfig} */
const nextConfig = {
  ...(isStaticExport ? { output: "export" } : {}),
  ...(!isStaticExport && firebaseAuthHelperOrigin
    ? {
        async rewrites() {
          return [
            {
              source: "/__/auth/:path*",
              destination: `${firebaseAuthHelperOrigin}/__/auth/:path*`,
            },
          ];
        },
      }
    : {}),
};

export default nextConfig;

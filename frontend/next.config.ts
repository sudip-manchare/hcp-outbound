import type { NextConfig } from "next";

const nextConfig: NextConfig = {
  // Produces a minimal traced runtime for the production Docker image.
  output: 'standalone',
  typescript: {
    // Test files use jest-dom matchers which need separate tsconfig handling
    // Type checking runs separately via `npm run type-check`
    ignoreBuildErrors: false,
  },
};

export default nextConfig;

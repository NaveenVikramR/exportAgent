import type { NextConfig } from "next";

const nextConfig: NextConfig = {
  // Self-contained server in .next/standalone, so the Docker image needs no npm install.
  output: "standalone",
};

export default nextConfig;

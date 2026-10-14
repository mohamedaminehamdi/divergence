import type { NextConfig } from "next";

/* GitHub Pages serves static files from /<repo>/, so that build exports static
   HTML under a base path. Every other build (local dev, a Node host) is left as
   a normal Next.js app. */
const pages = process.env.GITHUB_PAGES === "true";

const nextConfig: NextConfig = pages
  ? { output: "export", basePath: "/divergence", trailingSlash: true }
  : {};

export default nextConfig;

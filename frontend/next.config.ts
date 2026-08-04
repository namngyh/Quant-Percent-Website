import type { NextConfig } from "next";
import createNextIntlPlugin from "next-intl/plugin";

const withNextIntl = createNextIntlPlugin("./i18n/request.ts");

const nextConfig: NextConfig = {
  // Minimal production image containing the Node server and traced runtime
  // dependencies. Runtime server-only env vars remain configurable.
  output: "standalone",
};

export default withNextIntl(nextConfig);

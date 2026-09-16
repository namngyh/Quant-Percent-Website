import type { NextConfig } from "next";
import createNextIntlPlugin from "next-intl/plugin";

const withNextIntl = createNextIntlPlugin("./i18n/request.ts");

const nextConfig: NextConfig = {
  // Minimal production image containing the Node server and traced runtime
  // dependencies. Runtime server-only env vars remain configurable.
  output: "standalone",

  async redirects() {
    return [
      // The per-model pages were folded into /models. Anything that still
      // points at one — search results, a shared link, an old bookmark —
      // lands on the combined page rather than a 404. Permanent, so search
      // engines move their index entry instead of keeping a dead one.
      {
        source: "/:locale(vi|en)/models/:slug",
        destination: "/:locale/models",
        permanent: true,
      },
    ];
  },
};

export default withNextIntl(nextConfig);

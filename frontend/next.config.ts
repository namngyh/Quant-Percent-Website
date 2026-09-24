import type { NextConfig } from "next";
import createNextIntlPlugin from "next-intl/plugin";

const withNextIntl = createNextIntlPlugin("./i18n/request.ts");

const nextConfig: NextConfig = {
  // Minimal production image containing the Node server and traced runtime
  // dependencies. Runtime server-only env vars remain configurable.
  output: "standalone",

  // Dev only (production ignores it). The local stack that mirrors
  // production's shared session cookie serves the site as qp.localhost and the
  // Terminal as terminal.qp.localhost; without this, Next blocks its dev
  // assets and HMR when reached through those hosts.
  allowedDevOrigins: ["qp.localhost", "*.qp.localhost"],

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
      // The market-intelligence page was retired; the homepage now leads with
      // what replaced it as the reason to visit. Permanent for the same
      // reason as above.
      {
        source: "/:locale(vi|en)/market-intelligence",
        destination: "/:locale",
        permanent: true,
      },
      {
        source: "/market-intelligence",
        destination: "/",
        permanent: true,
      },
    ];
  },
};

export default withNextIntl(nextConfig);

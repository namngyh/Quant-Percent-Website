import type { MetadataRoute } from "next";
import { routing } from "@/i18n/routing";
import { publicModels } from "@/config/models";
import { STRATEGIES } from "@/config/strategies";
import { SITE_URL } from "@/lib/seo";

const STATIC_PATHS = [
  "",
  "/market-intelligence",
  "/models",
  "/performance",
  "/about",
  "/contact",
  "/legal",
  "/privacy",
  "/system-status",
];

export default function sitemap(): MetadataRoute.Sitemap {
  const paths = [
    ...STATIC_PATHS,
    ...publicModels().map((m) => `/models/${m.slug}`),
    ...STRATEGIES.map((s) => `/performance/${s.slug}`),
  ];
  const now = new Date();
  return paths.flatMap((path) =>
    routing.locales.map((locale) => ({
      url: `${SITE_URL}/${locale}${path}`,
      lastModified: now,
      alternates: {
        languages: Object.fromEntries(
          routing.locales.map((l) => [l, `${SITE_URL}/${l}${path}`])
        ),
      },
    }))
  );
}

import { publicModels } from "@/config/models";
import { freshness } from "@/lib/mock/market";
import { mockErrorResponse, mockStateFrom } from "@/lib/mock/state";

export function GET(req: Request) {
  const state = mockStateFrom(req);
  const err = mockErrorResponse(state);
  if (err) return err;
  return Response.json({
    ...freshness(state),
    models: publicModels().map((m) => ({
      slug: m.slug,
      name: m.name,
      code: m.code,
      markets: m.markets,
      category: m.category,
      status: m.status,
      version: m.version,
      horizons: m.horizons,
      access: m.access,
      locked: m.access === "members",
      featured: m.featured,
      tagline: m.tagline,
      key_output: m.keyOutput,
      sparkline: m.sparkline ?? null,
      sparkline_label: m.sparklineLabel ?? null,
      updated_at: m.updatedAt ?? new Date().toISOString(),
    })),
  });
}

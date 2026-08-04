import { getModel } from "@/config/models";
import { getModelResearch } from "@/config/model-research";
import { mockErrorResponse, mockStateFrom } from "@/lib/mock/state";

export async function GET(
  req: Request,
  { params }: { params: Promise<{ slug: string }> }
) {
  const state = mockStateFrom(req);
  const error = mockErrorResponse(state);
  if (error) return error;

  const { slug } = await params;
  const model = getModel(slug);
  if (!model || model.visibility !== "public") {
    return Response.json({ error: "not_found" }, { status: 404 });
  }

  return Response.json({
    slug: model.slug,
    name: model.name,
    code: model.code,
    markets: model.markets,
    category: model.category,
    status: model.status,
    version: model.version,
    horizons: model.horizons,
    access: model.access,
    locked: model.access === "members",
    featured: model.featured,
    tagline: model.tagline,
    key_output: model.keyOutput,
    sparkline: model.sparkline ?? null,
    sparkline_label: model.sparklineLabel ?? null,
    updated_at: model.updatedAt ?? new Date().toISOString(),
    show_forecast: model.show_forecast,
    show_performance: model.show_performance,
    description: model.description,
    architecture: model.architecture ?? null,
    research_profile: getModelResearch(slug) ?? null,
  });
}

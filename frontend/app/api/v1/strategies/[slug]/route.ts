import { getStrategy } from "@/config/strategies";
import { getHeadline, getProvenance } from "@/lib/performance/reports";

export async function GET(
  _request: Request,
  { params }: { params: Promise<{ slug: string }> }
) {
  const { slug } = await params;
  const strategy = getStrategy(slug);
  if (!strategy) {
    return Response.json({ error: "not_found" }, { status: 404 });
  }
  return Response.json({
    slug: strategy.slug,
    name: strategy.name,
    summary: strategy.summary,
    system_slug: strategy.systemSlug,
    result_type: strategy.resultType,
    asset: strategy.asset,
    timeframe: strategy.timeframe,
    benchmark: strategy.benchmark,
    period_start: strategy.periodStart,
    period_end: strategy.periodEnd,
    fees_note: strategy.feesNote,
    slippage_note: strategy.slippageNote,
    split_note: strategy.splitNote,
    seed_note: strategy.seedNote,
    model_version: strategy.modelVersion,
    code_version: strategy.codeVersion,
    headline: getHeadline(strategy),
    caveats: strategy.caveats,
    provenance: getProvenance(strategy.slug),
  });
}

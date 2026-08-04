import { STRATEGIES } from "@/config/strategies";
import { getHeadline } from "@/lib/performance/reports";
import { reportFreshness } from "@/lib/performance/freshness";
import { mockErrorResponse, mockStateFrom } from "@/lib/mock/state";

export function GET(req: Request) {
  const state = mockStateFrom(req);
  const err = mockErrorResponse(state);
  if (err) return err;
  return Response.json({
    ...reportFreshness(STRATEGIES[0].slug),
    strategies: STRATEGIES.map((s) => ({
      slug: s.slug,
      name: s.name,
      summary: s.summary,
      system_slug: s.systemSlug,
      result_type: s.resultType,
      asset: s.asset,
      timeframe: s.timeframe,
      benchmark: s.benchmark,
      period_start: s.periodStart,
      period_end: s.periodEnd,
      fees_note: s.feesNote,
      slippage_note: s.slippageNote,
      split_note: s.splitNote,
      seed_note: s.seedNote,
      model_version: s.modelVersion,
      code_version: s.codeVersion,
      headline: getHeadline(s),
    })),
  });
}

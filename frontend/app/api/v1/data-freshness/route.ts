import { freshness } from "@/lib/mock/market";
import { mockErrorResponse, mockStateFrom } from "@/lib/mock/state";

const FEEDS = ["VNINDEX", "VN30", "VN30F1M", "VN30_STOCKS"];

export function GET(req: Request) {
  const state = mockStateFrom(req);
  const err = mockErrorResponse(state);
  if (err) return err;
  const f = freshness(state);
  return Response.json({
    generated_at: f.generated_at,
    feeds: FEEDS.map((symbol) => ({
      id: symbol.toLowerCase(),
      symbol,
      data_as_of: f.data_as_of,
      is_stale: f.is_stale,
      delay_minutes: f.delay_minutes,
    })),
  });
}

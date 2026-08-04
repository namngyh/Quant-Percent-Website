import { forecastHistory } from "@/lib/mock/forecasts";
import { mockErrorResponse, mockStateFrom } from "@/lib/mock/state";

export async function GET(
  req: Request,
  { params }: { params: Promise<{ slug: string }> }
) {
  const { slug } = await params;
  const state = mockStateFrom(req);
  const err = mockErrorResponse(state);
  if (err) return err;
  const symbol = new URL(req.url).searchParams.get("symbol") ?? undefined;
  const history = forecastHistory(slug, symbol, state);
  if (!history) {
    return Response.json({ error: "not_found" }, { status: 404 });
  }
  return Response.json(history);
}

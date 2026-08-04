import { getSeries } from "@/lib/performance/reports";
import { reportFreshness } from "@/lib/performance/freshness";
import { mockErrorResponse, mockStateFrom } from "@/lib/mock/state";

export async function GET(
  req: Request,
  { params }: { params: Promise<{ slug: string }> }
) {
  const { slug } = await params;
  const state = mockStateFrom(req);
  const err = mockErrorResponse(state);
  if (err) return err;
  const series = getSeries(slug);
  if (!series) return Response.json({ error: "not_found" }, { status: 404 });
  return Response.json({ ...reportFreshness(slug), ...series });
}

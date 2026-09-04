import { getSimulation } from "@/lib/performance/reports";
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
  const sim = getSimulation();
  // Only the multi-seed run has a distribution over seeds
  if (!sim) return Response.json({ error: "not_available" }, { status: 404 });
  return Response.json({ ...reportFreshness(slug), ...sim });
}

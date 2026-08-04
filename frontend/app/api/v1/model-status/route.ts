import { publicModels } from "@/config/models";
import { freshness } from "@/lib/mock/market";
import { mockErrorResponse, mockStateFrom } from "@/lib/mock/state";

export function GET(req: Request) {
  const state = mockStateFrom(req);
  const err = mockErrorResponse(state);
  if (err) return err;
  const f = freshness(state);
  return Response.json({
    generated_at: f.generated_at,
    models: publicModels().map((m) => ({
      model_id: m.slug,
      status: m.status,
      last_run_at: m.status === "archived" ? null : f.data_as_of,
      healthy: m.status !== "archived",
    })),
  });
}

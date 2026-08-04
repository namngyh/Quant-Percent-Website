import { mockErrorResponse, mockStateFrom } from "@/lib/mock/state";

export function GET(req: Request) {
  const state = mockStateFrom(req);
  const err = mockErrorResponse(state);
  if (err) return err;
  const degraded = state === "stale";
  return Response.json({
    generated_at: new Date().toISOString(),
    services: [
      { id: "market_data", name: "Market Data Service", status: degraded ? "degraded" : "operational" },
      { id: "model_output", name: "Model Output Service", status: "operational" },
      { id: "performance", name: "Performance Service", status: "operational" },
      { id: "public_api", name: "Public API Gateway", status: "operational" },
      { id: "contact", name: "Contact Service", status: "operational" },
    ],
  });
}

import { getRiskDashboard } from "@/lib/mock/market";
import { mockErrorResponse, mockStateFrom } from "@/lib/mock/state";

export function GET(req: Request) {
  const state = mockStateFrom(req);
  return mockErrorResponse(state) ?? Response.json(getRiskDashboard(state));
}

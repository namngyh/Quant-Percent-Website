import { getHistory } from "@/lib/mock/market";
import { mockErrorResponse, mockStateFrom } from "@/lib/mock/state";

export async function GET(
  req: Request,
  { params }: { params: Promise<{ symbol: string }> }
) {
  const { symbol } = await params;
  const state = mockStateFrom(req);
  const err = mockErrorResponse(state);
  if (err) return err;
  const count = Math.min(
    500,
    Number(new URL(req.url).searchParams.get("count") ?? 250) || 250
  );
  return Response.json(getHistory(symbol.toUpperCase(), count, state));
}

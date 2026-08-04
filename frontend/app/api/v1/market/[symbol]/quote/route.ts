import { getQuote } from "@/lib/mock/market";
import { mockErrorResponse, mockStateFrom } from "@/lib/mock/state";

export async function GET(
  req: Request,
  { params }: { params: Promise<{ symbol: string }> }
) {
  const { symbol } = await params;
  const state = mockStateFrom(req);
  return (
    mockErrorResponse(state) ??
    Response.json(getQuote(symbol.toUpperCase(), state))
  );
}

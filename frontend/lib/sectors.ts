/**
 * ICB sector names, translated for display.
 *
 * `web.symbols.sector` stores the ICB supersector in English, because that is
 * what the exchange feed publishes and what the ingestion pipeline writes. The
 * database is the wrong place to localise it: the same row is read by the API,
 * the research notebooks and the daily job, and a Vietnamese string there would
 * have to be translated back for every non-display use.
 *
 * So the raw value stays English end to end and is translated at the last step,
 * here. An unmapped value falls through unchanged rather than showing a missing
 * key — a new sector appearing in the feed should read as an English label, not
 * as a broken page.
 *
 * The Vietnamese names follow the ICB classification as published for the
 * Vietnamese market, not a literal translation, so they match what a reader
 * sees on their broker's screen.
 */

const VI: Record<string, string> = {
  "automobiles & parts": "Ô tô & Phụ tùng",
  banks: "Ngân hàng",
  "basic resources": "Tài nguyên cơ bản",
  chemicals: "Hóa chất",
  "construction & materials": "Xây dựng & Vật liệu",
  "equity investment instruments": "Công cụ đầu tư vốn cổ phần",
  "financial services": "Dịch vụ tài chính",
  "food & beverage": "Thực phẩm & Đồ uống",
  "health care": "Y tế",
  "industrial goods & services": "Hàng & Dịch vụ công nghiệp",
  insurance: "Bảo hiểm",
  media: "Truyền thông",
  "oil & gas": "Dầu khí",
  "personal & household goods": "Hàng cá nhân & Gia dụng",
  "real estate": "Bất động sản",
  retail: "Bán lẻ",
  technology: "Công nghệ thông tin",
  telecommunications: "Viễn thông",
  "travel & leisure": "Du lịch & Giải trí",
  utilities: "Điện, nước & xăng dầu khí đốt",
  // The API's bucket for holdings with no sector on file.
  unclassified: "Chưa phân ngành",
};

/** Tolerates the "and" spelling and stray spacing seen in older feed rows. */
function normalise(raw: string) {
  return raw.trim().toLowerCase().replace(/\s+and\s+/g, " & ").replace(/\s+/g, " ");
}

/** Display name for an ICB sector, or the raw value when it is not mapped. */
export function sectorLabel(
  raw: string | null | undefined,
  locale: string,
): string | null {
  if (!raw) return null;
  if (!locale.startsWith("vi")) return raw;
  return VI[normalise(raw)] ?? raw;
}

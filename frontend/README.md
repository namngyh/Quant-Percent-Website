# Quant Percent — Website & Model Intelligence Platform (MVP)

Website thương hiệu + dashboard công khai đầu ra mô hình định lượng của **Quant Percent**, xây dựng theo đặc tả `Script.pdf` (phong cách tham chiếu Two Sigma). Song ngữ **VI/EN**; hỗ trợ mock offline và FastAPI/database trong production.

> Quant Percent hiện là tổ chức nghiên cứu định lượng. Website không phải nền tảng giao dịch; mọi dữ liệu trong mock mode là **dữ liệu minh họa**, không phải dữ liệu thị trường thật.

## Tech stack

- **Next.js 16** (App Router, Turbopack) + TypeScript
- **Tailwind CSS v4** + shadcn/ui (restyled theo design system trắng tối giản)
- **next-intl** — song ngữ `/vi/*` (mặc định) và `/en/*`
- **Apache ECharts** (`echarts/core`, tree-shaken, lazy render)
- **SWR** — data fetching + revalidate
- **Zod** — schema public API dùng chung client/server
- **Framer Motion** — reveal/count-up, tôn trọng `prefers-reduced-motion`
- **React Hook Form** — form liên hệ

## Chạy dự án

```bash
npm install
npm run dev        # http://localhost:3000 → redirect /vi
npm run build      # production build
npm start
```

Copy `.env.example` → `.env.local` (mọi biến đều tùy chọn trong mock mode).

## Cấu trúc

```
app/
├── [locale]/            # vi | en — mọi trang người dùng
│   ├── page.tsx         # Trang chủ (hero animation "%", market pulse, …)
│   ├── market-intelligence/  # 6 tab: Overview, VN-Index, VN30, VN30F1M, Stocks, Risk
│   ├── models/ + [slug]      # Danh mục & chi tiết mô hình
│   ├── performance/ + [slug] # Báo cáo hiệu suất (gắn nhãn loại kết quả)
│   ├── about/ contact/ legal/ privacy/ system-status/
├── api/v1/              # Mock API gateway (versioned, cùng shape với FastAPI sau này)
├── sitemap.ts robots.ts icon.svg
components/              # layout/ home/ market/ models/ performance/ charts/ states/ ui/
config/
├── models.ts            # Fixture/nguồn seed 12 mô hình
├── catalogue.json       # Snapshot xuất bản để backend seed database
└── strategies.ts        # ★ Catalog báo cáo hiệu suất
lib/
├── api/types.ts         # Zod schema §18 (ForecastRecord, freshness, …)
├── api/fetcher.ts       # SWR/request client: cookie, refresh và CSRF
├── models/ strategies/  # Server data layer: fixture dev / FastAPI production
├── mock/                # Sinh dữ liệu minh họa deterministic (seeded PRNG)
├── rate-limit.ts seo.ts format.ts
messages/vi.json en.json # Toàn bộ copy song ngữ
i18n/ proxy.ts           # next-intl routing
```

## Mock API

Mọi endpoint spec §19 được phục vụ tại `/api/v1/*`. Payload luôn kèm `data_as_of`, `generated_at`, `source_status`, `is_stale`, `delay_minutes`.

Giả lập trạng thái UI (spec §16.4) bằng query hoặc env:

```
/api/v1/market/overview?mock_state=stale     # ok | stale | empty | error | maintenance
MOCK_STATE=error npm run dev                 # áp dụng toàn cục
```

Production cùng origin: đặt `DATA_MODE=api`, `API_BASE_URL=http://api:8000` và
`NEXT_PUBLIC_AUTH_MODE=api`; reverse proxy `/api/*` sang FastAPI. Nếu API ở
domain riêng, đặt thêm `NEXT_PUBLIC_API_BASE_URL=https://api.example.com`.

## Thêm một mô hình mới

1. Mở `config/models.ts`, thêm một `ModelConfig` (slug, code, markets, category, status, `visibility: "public"`, horizons, tagline/description song ngữ, các cờ `show_*`).
2. Không cần sửa component — model tự xuất hiện ở: trang chủ (nếu `featured: true`), `/models` (kèm filter), `/models/[slug]`, `/api/v1/models`, `/api/v1/model-status`, sitemap.
3. Nếu model có báo cáo hiệu suất: thêm một `StrategyConfig` trong `config/strategies.ts` và trỏ `strategySlug`.
4. Quy tắc công khai (spec §9.2/§18): không đưa features, tham số, trọng số, tín hiệu vào lệnh vào bất kỳ trường nào.

Ẩn model: đổi `visibility: "hidden"` (hoặc `status: "archived"` để giữ trang nhưng đánh dấu lưu trữ).

## Dữ liệu hiệu suất (thật, không mock)

Khác với dữ liệu thị trường, mục `/performance` chạy trên **kết quả nghiên cứu thật** trích từ dự án Model-Modus:

- `config/performance/*.json` — dữ liệu tĩnh đã trích (`validation-2024`, `walk-forward`, `multiseed-test`), mỗi file có khối `provenance` ghi rõ file nguồn và phiên bản code sinh ra số.
- `config/strategies.ts` — metadata 3 báo cáo: loại kết quả, giai đoạn, phí/trượt giá, cách chia dữ liệu, phiên bản mô hình/mã nguồn và danh sách `caveats` hiển thị ngay đầu trang chi tiết.
- `lib/performance/reports.ts` — chuyển dữ liệu thành payload API; **không sinh số ngẫu nhiên**.

Mock mode đọc các file trên trực tiếp. Production seed snapshot vào database;
danh sách, metadata, caveat, provenance, chart và metric của `/performance`
đều đọc lại qua FastAPI/database ở runtime.

Quy ước %: quy trên vốn danh nghĩa **1.000 điểm chỉ số** (100.000.000 VND, 100.000 VND/điểm), drawdown tính trên đỉnh vốn — đã kiểm chứng tái lập đúng `net_pct` và `max_dd_pct` của dự án gốc.

**Khi có kết quả chạy lại** (sau bản sửa khớp lệnh 04/07/2026): chạy lại script trích trong `Model-Modus`, ghi đè 3 file JSON, cập nhật `codeVersion` trong `config/strategies.ts` và bỏ `restatementNote` khỏi messages nếu không còn phù hợp.

## Quyền truy cập model & đăng nhập

Mỗi model trong `config/models.ts` có cờ `access`:

- `"public"` — ai cũng xem được card lẫn trang chi tiết.
- `"members"` — card bị làm mờ sau lớp khóa ở `/models`, trang chi tiết chỉ hiện phần giới thiệu; nội dung còn lại thay bằng panel "Cần đăng nhập".

Đổi cờ này là cách duy nhất để chỉ định model nào cho xem trước — không cần sửa component.

`lib/auth/auth-context.tsx` có hai chế độ. Mock mode dùng localStorage để phát
triển offline; API mode gọi `/api/v1/auth/*` và dùng cookie httpOnly của FastAPI.
Backend vẫn là lớp kiểm quyền cuối cùng: endpoint output của model members-only
trả 403 khi không có phiên hợp lệ.

## Form liên hệ

Trong mock mode, `POST /api/v1/contact` lưu JSONL cục bộ. Trong production,
reverse proxy chuyển endpoint này sang FastAPI để lưu vào database và gửi email
thông báo nếu được cấu hình.

## Nguyên tắc nội dung (bắt buộc giữ khi sửa)

- Không mô tả Quant Percent như quỹ đang huy động vốn; không CTA "Đầu tư ngay".
- Tín hiệu công khai chỉ dùng: Bullish / Neutral / Defensive / High Risk / Low Conviction.
- Hiệu suất luôn gắn nhãn Backtest / Out-of-sample / Walk-forward / Paper trading; không trộn.
- Chỉ số thiếu hiển thị là thiếu — không thay bằng 0.
- Disclaimer pháp lý ở footer + trang model/performance; nội dung Legal cần luật sư VN rà soát trước production.

## Deploy

- Build tĩnh + SSR hybrid chuẩn Next.js — deploy được trên Vercel hoặc Node server (`npm run build && npm start`).
- Production cần HTTPS, đặt `NEXT_PUBLIC_SITE_URL` đúng domain để sitemap/hreflang/canonical chính xác.
- Khuyến nghị có môi trường staging trước production (spec §26).

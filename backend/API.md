# Quant Percent API

Base path: `/api/v1`. OpenAPI/Swagger có tại `/docs` ở môi trường dev và
staging; production tắt Swagger công khai.

## Nhóm endpoint

| Nhóm | Endpoint |
|---|---|
| Market | `GET /market/overview`, `/{symbol}/quote`, `/{symbol}/history`, `/vn30/constituents`, `/risk` |
| Models | `GET /models`, `/{slug}`, `/{slug}/latest`, `/{slug}/history` |
| Performance | `GET /strategies`, `/{slug}`, `/{slug}/performance`, `/{slug}/metrics`, `/{slug}/simulations` |
| System | `GET /status`, `/data-freshness`, `/model-status` |
| Forms | `POST /contact`, `/investor-interest` |
| Auth | `POST /auth/register`, `/login`, `/logout`, `/refresh`, `/forgot-password`, `/reset-password`, `/verify-email`; `GET /auth/me` |

Ngoài prefix: `GET /healthz` và `GET /readyz`.

## Hợp đồng chung

- Dữ liệu thị trường/model/performance có freshness gồm `data_as_of`,
  `generated_at`, `source_status`, `is_stale`, `delay_minutes`.
- Metric thiếu được trả `null`, không thay bằng `0`.
- Model `members` vẫn công khai metadata; `/latest` và `/history` trả 403 nếu
  chưa đăng nhập.
- Bốn model `raemf-mc`, `rarf-fhe`, `dynamic-graph`, `msdp` hiện là
  research-only và trả 404 `not_available` ở `/latest` cho đến khi có runner.

## Auth và lỗi

- Phiên dùng cookie `qp_access`, `qp_refresh` và double-submit CSRF `qp_csrf`.
- Request thay đổi trạng thái khi đã đăng nhập phải gửi `X-CSRF-Token` trùng
  cookie `qp_csrf`.
- Các mã thường gặp: 400 validation, 401 chưa đăng nhập, 403 members-only/CSRF,
  404 không tồn tại hoặc chưa có output, 429 rate limit, 503 dependency chưa sẵn sàng.

Hợp đồng máy đọc được là OpenAPI sinh từ FastAPI; script đối chiếu frontend:

```powershell
npm run check:api -- http://localhost:8000
```

#!/usr/bin/env bash
#
# Deploy quantpercent.com lên VPS.
#
# Chạy được hai cách, kết quả giống hệt nhau:
#   - Bằng tay:      ssh vào VPS rồi gõ  bash ~/Quant-Percent-Website/backend/deploy/deploy.sh
#   - Tự động:       GitHub Actions gọi file này sau khi test đã xanh
#
# Mỗi bước đều in ra "==> n/6" nên đọc log là biết nó đang làm gì và chết ở đâu.

set -euo pipefail
# -e            gặp lỗi là dừng ngay, KHÔNG chạy tiếp các bước sau.
#               Không có nó thì build fail vẫn báo "deploy thành công" — kiểu
#               hỏng tệ nhất, vì bạn tưởng đã lên bản mới mà thật ra chưa.
# -u            dùng biến chưa khai báo là lỗi, tránh gõ nhầm tên biến rồi
#               lặng lẽ chạy với chuỗi rỗng.
# -o pipefail   lệnh chết giữa chuỗi ống (a | b) cũng tính là lỗi.

# Tự tìm thư mục repo từ vị trí của chính file này, nên script không phụ thuộc
# vào việc bạn đang đứng ở đâu khi gọi nó.
DEPLOY_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_DIR="$(cd "$DEPLOY_DIR/../.." && pwd)"

# Gói cả cụm lệnh vào một mảng để khỏi gõ lại 4 lần ở dưới.
#
# PHẢI có đủ CẢ HAI file -f. compose.override.yml giữ hai thứ sống còn: volume
# chứng chỉ Cloudflare cho Caddy, và cổng PostgreSQL mở cho VPN. Chạy thiếu nó
# thì Compose vẫn coi đây là stack "quantpercent-production" và chỉnh nó về
# đúng mô tả trong compose.production.yml — tức là gỡ mất cả hai, Caddy chết
# vì không thấy chứng chỉ, web sập.
COMPOSE=(
  docker compose
  --env-file .env.production
  -f compose.production.yml
  -f compose.override.yml
)

echo "==> 1/6 Kiểm tra file cấu hình bí mật"
cd "$DEPLOY_DIR"
if [ ! -f .env.production ]; then
  echo "LỖI: không thấy $DEPLOY_DIR/.env.production" >&2
  echo "File này chứa mật khẩu nên cố ý không nằm trong Git. Tạo nó từ" >&2
  echo ".env.production.example rồi điền đầy đủ trước khi deploy." >&2
  exit 1
fi

# Chứng chỉ Cloudflare Origin nằm trên máy chủ chứ không trong Git (khoá riêng
# không bao giờ được commit). Kiểm tra ngay đây để nếu thiếu thì dừng lập tức,
# thay vì build xong 5 phút rồi mới phát hiện Caddy không lên được.
for cert in /etc/caddy/certs/origin.pem /etc/caddy/certs/origin-key.pem; do
  if [ ! -f "$cert" ]; then
    echo "LỖI: không thấy $cert" >&2
    echo "Caddyfile dùng chứng chỉ Cloudflare Origin để chạy HTTPS phía sau" >&2
    echo "proxy của Cloudflare. Thiếu file này thì web không lên được TLS." >&2
    exit 1
  fi
done

echo "==> 2/6 Lấy code mới nhất từ GitHub"
cd "$REPO_DIR"
git fetch --prune origin
git reset --hard origin/main
# reset --hard làm thư mục trên VPS giống hệt origin/main.
# Nghĩa là MỌI sửa tay trực tiếp trên server sẽ bị xoá — đây là chủ ý: server
# phải là bản sao y hệt GitHub, nếu không sẽ tới lúc không ai biết production
# đang thật sự chạy code gì.
#
# ĐỪNG BAO GIỜ thêm `git clean -fdx` vào đây. Nó xoá cả file bị gitignore,
# tức là xoá luôn deploy/.env.production, và cả stack sẽ không khởi động lại
# được vì mất hết mật khẩu database.

echo "==> 3/6 Build lại image và khởi động"
cd "$DEPLOY_DIR"
"${COMPOSE[@]}" up -d --build
# --build  build lại image từ code vừa kéo về. Thiếu cờ này thì container vẫn
#          chạy code cũ dù git đã cập nhật — lỗi hay gặp nhất khi deploy tay.
# -d       chạy nền.
# Compose chỉ tạo lại container nào thật sự thay đổi, nên TimescaleDB và Redis
# không bị restart và dữ liệu không bị gián đoạn.
#
# GHI NHỚ CHO LẦN SAU: nếu bản deploy nào có thêm bảng mới trong database thì
# phải chèn dòng dưới vào TRƯỚC lệnh `up`, nếu không API sẽ chạy với schema cũ:
#   "${COMPOSE[@]}" --profile tools run --rm migrate

echo "==> 4/6 Chờ web trả lời (tối đa 90 giây)"
DOMAIN="$(awk -F= '/^DOMAIN=/{print $2; exit}' .env.production)"
if [ -z "$DOMAIN" ]; then
  echo "LỖI: .env.production không có dòng DOMAIN=" >&2
  exit 1
fi

healthy=0
for _ in $(seq 1 45); do
  if curl -fsS --max-time 5 "https://$DOMAIN/healthz" >/dev/null 2>&1; then
    healthy=1
    break
  fi
  sleep 2
done

if [ "$healthy" -ne 1 ]; then
  echo "LỖI: $DOMAIN không phản hồi /healthz sau 90 giây." >&2
  echo "Web có thể đang hỏng. Log 40 dòng cuối của api:" >&2
  "${COMPOSE[@]}" logs --tail=40 api >&2 || true
  exit 1
fi
echo "https://$DOMAIN/healthz OK"

# /readyz kiểm tra sâu hơn: database và Redis có kết nối được không.
# Không cho fail cả lần deploy vì Redis chỉ làm giảm chất lượng chứ không chết
# web — nhưng phải in ra để bạn thấy.
echo "Trạng thái phụ thuộc:"
curl -fsS --max-time 5 "https://$DOMAIN/readyz" || echo "(readyz không xanh — xem lại database/redis)"
echo

echo "==> 5/6 Trạng thái các container"
"${COMPOSE[@]}" ps

echo "==> 6/6 Dọn image cũ"
docker image prune -f
# Mỗi lần --build để lại một image cũ không ai dùng. VPS dung lượng có hạn,
# vài chục lần deploy là đầy ổ. Lệnh này chỉ xoá image không container nào
# tham chiếu tới, nên an toàn với mọi thứ đang chạy.

echo
echo "Deploy xong: https://$DOMAIN"

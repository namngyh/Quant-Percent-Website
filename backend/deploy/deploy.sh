#!/usr/bin/env bash
#
# Deploy quantpercent.com lên VPS.
#
# Chạy được hai cách, kết quả giống hệt nhau:
#   - Bằng tay:      ssh vào VPS rồi gõ  bash ~/Quant-Percent-Website/backend/deploy/deploy.sh
#   - Tự động:       GitHub Actions gọi file này sau khi test đã xanh
#
# Mỗi bước đều in ra "==> n/9" nên đọc log là biết nó đang làm gì và chết ở đâu.

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

echo "==> 1/9 Kiểm tra file cấu hình bí mật"
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

echo "==> 2/9 Lấy code mới nhất từ GitHub"
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

# `git reset --hard` vừa ghi đè chính file đang chạy. Bash đọc script theo
# offset byte chứ không nạp hết vào bộ nhớ, nên từ đây trở đi nó đọc tiếp một
# file đã khác — hoặc chạy nhầm dòng, hoặc chạy đúng nhưng là LOGIC CŨ.
#
# Đó là lý do bước nạp catalogue thêm vào hôm nay không chạy ở lần deploy đầu
# tiên: bản mới đã nằm trên đĩa nhưng bản đang thực thi vẫn là bản trước đó.
# Mọi sửa đổi deploy.sh vì thế đều trễ đúng một lần deploy, và tệ hơn là
# script có thể chạy sai giữa chừng mà không báo gì.
#
# Nạp lại chính mình một lần, từ bản vừa kéo về. Biến QP_DEPLOY_RELOADED chặn
# vòng lặp vô hạn.
if [ "${QP_DEPLOY_RELOADED:-}" != "1" ]; then
  echo "    Nạp lại deploy.sh từ bản vừa kéo về..."
  export QP_DEPLOY_RELOADED=1
  exec bash "$DEPLOY_DIR/deploy.sh" "$@"
fi

echo "==> 3/9 Build image từ code vừa kéo về"
cd "$DEPLOY_DIR"
"${COMPOSE[@]}" build
# Tách hẳn khỏi `up` (trước đây là `up -d --build`) để bước migration ở dưới
# chạy được bằng ĐÚNG image mới. Nếu build gộp vào `up`, thứ tự sẽ là
# "khởi động code mới rồi mới nâng schema" — tức là có một quãng code mới chạy
# trên schema cũ, đúng thứ ta đang muốn tránh.
#
# Build ở đây chưa đụng gì tới container đang chạy: web vẫn phục vụ bản cũ
# suốt lúc build.

echo "==> 4/9 Cập nhật schema database"
"${COMPOSE[@]}" --profile tools run --rm migrate
# Đây là bước trước kia chỉ tồn tại dưới dạng một dòng comment nhắc nhở, và
# nhắc nhở thì có ngày quên. Quên nó thì API mới chạy với schema cũ và vỡ ở
# mọi truy vấn chạm vào cột chưa tồn tại.
#
# `alembic upgrade head` là idempotent: không có migration mới thì nó không
# làm gì cả, nên chạy mỗi lần deploy là vô hại.
#
# Chạy TRƯỚC `up` là có chủ ý, và nó an toàn vì migration trong repo này chỉ
# thêm cột/bảng chứ không xoá: giữa hai bước, container CŨ vẫn chạy trên
# schema MỚI, mà thêm cột thì code cũ không hề hấn gì. Nếu sau này có
# migration xoá hay đổi tên cột thì phải tách làm hai lần deploy — thêm trước,
# dọn sau — chứ không được để chung.
#
# `set -e` ở đầu file lo phần còn lại: migration hỏng là dừng ngay tại đây,
# `up` không chạy, và web vẫn đang chạy bản cũ nguyên vẹn.
#
# Lệnh này kéo theo hai service khác qua `depends_on`, và đó là điều mong muốn:
#   - timescaledb  phải healthy trước khi có gì để nâng cấp
#   - db-role-init chạy scripts/create_role.sql, idempotent, chỉ đặt lại mật
#                  khẩu và quyền cho qp_web
# Nghĩa là mỗi lần deploy đều chạy lại db-role-init. Vô hại, và nó đòi
# QP_WEB_PASSWORD — biến mà service `api` vốn đã bắt buộc phải có, nên không
# phát sinh yêu cầu mới nào.

echo "==> 5/9 Khởi động"
"${COMPOSE[@]}" up -d
# -d  chạy nền.
# Compose chỉ tạo lại container nào thật sự thay đổi, nên TimescaleDB và Redis
# không bị restart và dữ liệu không bị gián đoạn.

echo "==> 6/9 Chờ web trả lời (tối đa 90 giây)"
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

# Nội dung trang model (tên, mô tả, số liệu nghiên cứu, báo cáo hiệu suất)
# nằm trong bảng web.models chứ không nằm trong bản build của frontend. Thiếu
# bước này thì deploy vẫn xanh, web vẫn chạy, nhưng trang hiển thị nội dung
# của lần seed trước — đúng kiểu hỏng im lặng đã xảy ra với trang
# DynamicGraph: mô hình chạy mỗi ngày mà trang đứng ở số liệu cũ cả tháng.
#
# Container api đã mount sẵn frontend/config tại /catalogue/config, nên chạy
# ngay trong đó thay vì cần Python trên máy chủ.
echo "==> 7/9 Nạp catalogue vào database"
if ! "${COMPOSE[@]}" exec -T api python -m scripts.seed_catalogue --frontend /catalogue; then
  echo "LỖI: nạp catalogue thất bại." >&2
  echo "Web đang chạy nhưng nội dung trang model là của lần nạp trước." >&2
  echo "Chạy lại tay:" >&2
  echo "  cd $DEPLOY_DIR && ${COMPOSE[*]} exec -T api python -m scripts.seed_catalogue --frontend /catalogue" >&2
  exit 1
fi

echo "==> 8/9 Trạng thái các container"
"${COMPOSE[@]}" ps

echo "==> 9/9 Dọn image cũ"
docker image prune -f
# Mỗi lần --build để lại một image cũ không ai dùng. VPS dung lượng có hạn,
# vài chục lần deploy là đầy ổ. Lệnh này chỉ xoá image không container nào
# tham chiếu tới, nên an toàn với mọi thứ đang chạy.

echo
echo "Deploy xong: https://$DOMAIN"

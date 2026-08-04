# WEBSITE SPEC — Model Modus Landing Page

> Đặc tả đầy đủ để build lại website giới thiệu team + sản phẩm Model Modus.
> Phong cách tham chiếu: **blockbase.co** (dark premium fintech).
> Trạng thái: bản thiết kế v1 — mọi chỗ đánh dấu `[...]` là placeholder chờ điền nội dung thật.

---

## 1. TỔNG QUAN

| Mục | Giá trị |
|---|---|
| Loại | Single-page landing (1 trang, scroll dọc, anchor navigation) |
| Ngôn ngữ | Tiếng Việt (`<html lang="vi">`) |
| Tech stack | HTML + CSS + Vanilla JS thuần — không framework, không build step |
| Cấu trúc file | `index.html` + `assets/style.css` + `assets/main.js` |
| Title | `Model Modus — Hệ thống giao dịch định lượng phái sinh` |
| Meta description | `Giới thiệu đội ngũ và sản phẩm Model Modus — hệ thống giao dịch định lượng cho hợp đồng tương lai VN30F1M.` |
| Lưu ý deploy | Phải serve qua HTTP (static server bất kỳ). Mở `file://` trực tiếp có thể bị chặn CSS trong một số môi trường |

**Nguyên tắc nội dung:** KHÔNG bịa số hiệu suất. Mọi con số/thông tin chưa có → placeholder in nghiêng xám.

---

## 2. DESIGN SYSTEM

### 2.1 Màu sắc (CSS variables trên `:root`)

| Token | Hex/Giá trị | Dùng cho |
|---|---|---|
| `--bg` | `#0a0d12` | Nền chính (đen xanh navy) |
| `--bg-soft` | `#0f141c` | Nền section xen kẽ (about, technology, partners) |
| `--bg-card` | `#121924` | Nền card |
| `--line` | `rgba(255,255,255,0.08)` | Border, kẻ phân cách |
| `--text` | `#e8eaee` | Chữ chính |
| `--text-dim` | `#9aa3b2` | Chữ phụ |
| `--text-faint` | `#5c6575` | Chữ mờ / placeholder |
| `--accent` | `#d4a94e` | **Vàng đồng** — màu nhấn chủ đạo (eyebrow, nút, viền, số liệu) |
| `--accent-soft` | `rgba(212,169,78,0.12)` | Nền hover nhấn |
| Accent hover | `#e6c069` | Nút primary khi hover |
| Chữ trên nền vàng | `#14100a` | Text trong nút primary/badge |
| Footer bg | `#070a0e` | Đậm hơn nền chính |

### 2.2 Typography

| Token | Giá trị |
|---|---|
| `--font-display` | `"Playfair Display", Georgia, serif` — heading (Google Fonts, weight 500/600/700) |
| `--font-body` | `"Inter", -apple-system, "Segoe UI", sans-serif` — body (weight 300/400/500/600/700) |
| Body | weight 300, `line-height: 1.7`, antialiased |
| Hero title | display font, 600, `clamp(44px, 7vw, 88px)`, line-height 1.08 |
| Section title | display font, 600, `clamp(32px, 4.5vw, 52px)`, line-height 1.15 |
| Eyebrow (nhãn nhỏ trên title) | 12px, `letter-spacing: 0.35em`, màu accent, weight 600, uppercase |
| Lead paragraph | 20px, weight 400 |
| Nav link | 12px, weight 600, `letter-spacing: 0.18em`, uppercase |
| Nút | 13px, weight 600, `letter-spacing: 0.18em`, uppercase |

Google Fonts import:
```
https://fonts.googleapis.com/css2?family=Playfair+Display:wght@500;600;700&family=Inter:wght@300;400;500;600;700&display=swap
```

### 2.3 Layout

- Container: `max-width: 1180px`, padding ngang 24px, căn giữa
- Section padding dọc: 110px (desktop) / 80px (mobile)
- Nền section xen kẽ: `--bg` → `--bg-soft` → `--bg` → … tạo nhịp
- Border radius: 2px (gần vuông — chất "institutional")
- `scroll-behavior: smooth`

### 2.4 Components

**Nút (3 biến thể):** padding `14px 34px`, radius 2px, transition 0.3s
- `btn-primary`: nền accent, chữ `#14100a`; hover: sáng hơn + `translateY(-2px)`
- `btn-ghost`: viền `--line`, chữ trắng; hover: viền + chữ accent
- `btn-outline`: viền accent, chữ accent, nền trong; hover nền `--accent-soft`; biến thể `.disabled`: viền/chữ mờ

**Link mũi tên (`link-arrow`):** chữ accent 13px uppercase + `→` sau, hover mũi tên trượt sang phải (margin-left 10→18px)

**Placeholder style (quan trọng):**
- `.placeholder-inline`: chữ `--text-faint`, in nghiêng
- `.placeholder-block`: như trên + `border-left: 2px dashed` + padding-left 14px

**Spec table (trong product card):** `<dl>` các hàng `dt` (nhãn, chữ mờ, trái) — `dd` (giá trị, chữ trắng, phải), mỗi hàng `padding: 13px 0` + border-bottom `--line`, font 13.5px

---

## 3. CẤU TRÚC TRANG (8 section, theo form blockbase.co)

### 3.1 NAV (fixed top)

- Trong suốt ở đầu trang; khi `scrollY > 40` → nền `rgba(10,13,18,0.92)` + `backdrop-filter: blur(12px)` + border-bottom
- **Logo trái:** ô vuông 38px viền accent chứa chữ "M" serif + chữ "MODEL MODUS" letter-spacing 0.3em
- **Menu phải** (có dropdown hover):

| Mục | Dropdown |
|---|---|
| GIỚI THIỆU | Về chúng tôi → `#about` · Đội ngũ → `#team` · Tuyển dụng *(sắp có, mờ)* |
| SẢN PHẨM | nhãn nhóm "Sản phẩm phái sinh" → Model Modus `#modus` · nhãn "Danh mục khác" → *Đang cập nhật… (mờ)* |
| CÔNG NGHỆ | → `#technology` |
| TIN TỨC & GÓC NHÌN | → `#insights` |
| LIÊN HỆ | nút viền accent → `#contact` |

- Dropdown: nền `--bg-card`, viền `--line`, fade+slide 0.25s khi hover
- **Mobile (<980px):** menu ẩn, hiện burger 3 gạch → mở menu dọc full-width

### 3.2 HERO (`#home`, min-height 100vh)

- **Nền:** `<canvas>` vẽ nến + lưới trừu tượng, animate bằng `requestAnimationFrame` (xem §5.3), opacity 0.55, phủ radial-gradient tối dần ra mép
- **Title 3 dòng** (mỗi dòng 1 `<span>` reveal lần lượt):
  > Kỷ luật
  > của thuật toán.
  > **Lợi thế của dữ liệu.** *(dòng 3 màu accent)*
- **Sub** (max-width 560px, 18px, chữ dim):
  > Chúng tôi xây dựng hệ thống giao dịch định lượng cho thị trường phái sinh Việt Nam — nơi mọi quyết định được đo bằng xác suất, không phải cảm xúc.
- **2 nút:** `Khám phá Model Modus` (primary → `#modus`) · `Về chúng tôi` (ghost → `#about`)
- **Scroll hint:** viên con nhộng 22×38px viền mờ, chấm accent bên trong animate rơi xuống (loop 1.8s)

### 3.3 VỀ CHÚNG TÔI (`#about`, nền `--bg-soft`)

Layout 2 cột (1fr / 1.2fr, gap 70px):
- **Trái:** eyebrow `VỀ CHÚNG TÔI` + title:
  > Giao dịch là một bài toán **kỹ thuật.** *(từ cuối accent)*
- **Phải:**
  - Lead: > Chúng tôi tin rằng lợi thế bền vững trên thị trường tài chính đến từ nghiên cứu nghiêm túc: dữ liệu sạch, kiểm định trung thực và quản trị rủi ro có kỷ luật.
  - Body: > Đội ngũ của chúng tôi kết hợp machine learning, reinforcement learning và kinh nghiệm thực chiến trên thị trường phái sinh Việt Nam để xây dựng những hệ thống giao dịch tự động — minh bạch về phương pháp, khắt khe về kiểm chứng.
  - `[Phần giới thiệu chi tiết về team — lịch sử hình thành, tầm nhìn, sứ mệnh — sẽ được cập nhật]` *(placeholder-block)*
  - Link arrow `TÌM HIỂU THÊM` → `#team`
- **Hàng stats** (4 cột, border-top, margin-top 90px) — số display font 44px accent, nhãn 13px dim. Cả 4 số đang là `—`:
  1. Năm dữ liệu nghiên cứu
  2. Thành viên đội ngũ
  3. Sản phẩm đang vận hành
  4. Đối tác đồng hành

### 3.4 SẢN PHẨM (`#products`)

- Eyebrow `SẢN PHẨM CỦA CHÚNG TÔI` + title `Danh mục sản phẩm` (căn giữa)
- Sub: > Mỗi sản phẩm là một hệ thống hoàn chỉnh — từ nghiên cứu, kiểm định đến vận hành.
- **Tag danh mục** căn giữa, viền accent, letter-spacing 0.3em: `SẢN PHẨM PHÁI SINH`
- **Grid 3 card** (giống fund card blockbase — bảng spec + nút):

**Card 1 — MODEL MODUS (`#modus`, featured):**
- Viền accent + gradient vàng nhạt từ trên xuống; badge nền vàng `FLAGSHIP`
- Mô tả: > Hệ thống giao dịch thuật toán cho hợp đồng tương lai chỉ số VN30 (VN30F1M), vận hành bởi mô hình học tăng cường sâu.
- Spec table:

| Nhãn | Giá trị |
|---|---|
| Thị trường | Hợp đồng tương lai VN30F1M |
| Khung thời gian | M5 — giao dịch trong ngày |
| Công nghệ lõi | LSTM + Deep Reinforcement Learning (PPO) |
| Quản trị rủi ro | Stop-loss & trailing thích ứng theo biến động |
| Kiểm định | Walk-forward, multi-seed, chống data-leakage |
| Hiệu suất | `[Sẽ cập nhật]` |
| Trạng thái | `[Sẽ cập nhật]` |

- Nút outline `KHÁM PHÁ` → `#technology`

**Card 2 & 3 — placeholder (class `coming`, opacity 0.75):**
- Tên `[SẢN PHẨM 2]` / `[SẢN PHẨM 3]`, badge viền mờ `SẮP RA MẮT`
- Mô tả: `[Mô tả sản phẩm sẽ được cập nhật]`
- Spec table 5 hàng (Thị trường / Khung thời gian / Công nghệ lõi / Quản trị rủi ro / Trạng thái) toàn `—`
- Nút disabled `SẮP CÔNG BỐ`

Hover mọi card: `translateY(-6px)` + viền vàng nhạt.

### 3.5 CÔNG NGHỆ (`#technology`, nền `--bg-soft`)

- Eyebrow `CÔNG NGHỆ` + title `Bên trong Model Modus` (căn giữa)
- Sub: > Một kiến trúc nhiều tầng — mỗi tầng giải một bài toán riêng, tất cả phục vụ một mục tiêu: tối đa hóa giá trị kỳ vọng của từng quyết định.
- **Grid 6 card** (3 cột), mỗi card: số thứ tự serif accent (01–06) + h3 17px + đoạn mô tả 14px dim:

| # | Tiêu đề | Nội dung |
|---|---|---|
| 01 | Tầng tín hiệu | Ba hệ thống tín hiệu độc lập — mỗi hệ thống nhìn thị trường qua một lăng kính riêng (chu kỳ, xu hướng, động lượng) — cung cấp góc nhìn đa chiều cho mô hình trung tâm. |
| 02 | Bộ não quyết định | Mạng LSTM ghi nhớ 255 nến gần nhất, kết hợp học tăng cường (PPO) để ra quyết định vào lệnh / thoát lệnh theo mức độ tự tin — không phải quyết định nhị phân. |
| 03 | Nhận diện trạng thái thị trường | Mô hình Hidden Markov phân loại thị trường theo thời gian thực: dòng tiền tăng, dòng tiền giảm, đi ngang hay hỗn loạn — để bộ não hiểu bối cảnh trước khi hành động. |
| 04 | Quản trị rủi ro thích ứng | Stop-loss và trailing-stop tự co giãn theo biến động dự báo (GARCH), giám sát ở độ phân giải từng phút — rủi ro được kiểm soát liên tục, không chờ hết nến. |
| 05 | Kiểm định trung thực | Quy trình chống data-leakage nghiêm ngặt: dữ liệu kiểm định được "niêm phong", walk-forward theo thời gian, chạy đa hạt giống (multi-seed) với khoảng tin cậy thống kê. |
| 06 | Mô phỏng sát thực tế | Backtest mô phỏng khớp lệnh trung thực: gap giá, phiên ATC, ngày đáo hạn hợp đồng, chi phí giao dịch — để con số trên giấy gần nhất với con số trên tài khoản. |

### 3.6 ĐỘI NGŨ (`#team`)

- Eyebrow `ĐỘI NGŨ` + title `Những người đứng sau` + sub placeholder `[Giới thiệu chung về đội ngũ sẽ được cập nhật]`
- **Grid 4 card**, mỗi card: avatar vuông (aspect-ratio 1, nền card + radial glow vàng nhạt, dấu `?` serif lớn ở giữa) + `[Họ tên]` + `[Vị trí]`

### 3.7 ĐỐI TÁC (`#partners`, nền `--bg-soft`)

- Eyebrow `ĐỐI TÁC` + title `Đối tác của chúng tôi`
- **3 nhóm** (map từ Services / Bank & Custodian / Exchanges của blockbase):
  1. `DỊCH VỤ` — 2 ô `[Logo]`
  2. `CÔNG TY CHỨNG KHOÁN` — 2 ô `[Logo]`
  3. `CÔNG NGHỆ & DỮ LIỆU` — 2 ô `[Logo]`
- Ô logo: 130×62px, viền dashed `--line`, chữ placeholder giữa

### 3.8 TIN TỨC & GÓC NHÌN (`#insights`)

- Header 2 bên: trái = eyebrow `TIN TỨC & GÓC NHÌN` + title `Góc nhìn từ đội ngũ`; phải = link arrow `XEM TẤT CẢ`
- **Grid 3 card bài viết:** thumbnail 16:9 (nền card + gradient vàng chéo nhạt) + `[Ngày đăng]` 12px + `[Tiêu đề bài viết sẽ được cập nhật]` 16px

### 3.9 FOOTER / LIÊN HỆ (`#contact`, nền `#070a0e`)

- **Hàng trên** (2 cột, border-bottom):
  - Trái — tagline display font `clamp(28px, 3.5vw, 42px)`:
    > Kỷ luật của thuật toán.
    > **Lợi thế của dữ liệu.** *(dòng 2 accent)*
  - Phải — 3 khối liên hệ (nhãn 11px accent letter-spacing 0.3em):
    - HOTLINE → `[Số điện thoại]`
    - EMAIL → `[Địa chỉ email]`
    - ĐỊA CHỈ → `[Địa chỉ văn phòng]`
- **Hàng dưới:**
  - Disclaimer (12px, chữ faint, max-width 760px):
    > Thông tin trên website chỉ nhằm mục đích giới thiệu sản phẩm và không cấu thành lời khuyên đầu tư. Giao dịch phái sinh tiềm ẩn rủi ro; hiệu suất trong quá khứ không đảm bảo kết quả tương lai.
  - Copyright: `Copyright © 2026 [Tên công ty/team]. All rights reserved.`

---

## 4. RESPONSIVE

| Breakpoint | Thay đổi |
|---|---|
| `≤980px` | Nav links ẩn → burger + mobile menu dọc; nav luôn có nền đặc. About 2 cột → 1 cột. Stats 4 → 2 cột. Product/Tech/Insight/Partner grid → 1 cột. Team → 2 cột. Footer top → 1 cột. Section padding 110 → 80px. Insights header xếp dọc |
| `≤520px` | Team → 1 cột. Hero title 42px |

Không được có scroll ngang ở mọi khổ (`overflow-x: hidden` trên body).

---

## 5. JAVASCRIPT (3 behavior + 1 canvas)

### 5.1 Nav scroll state
`scroll` listener (passive): `scrollY > 40` → thêm class `scrolled` (nền đặc + blur + shadow). Gọi 1 lần lúc load.

### 5.2 Mobile menu
Click burger → toggle class `open` trên menu; click bất kỳ link nào trong menu → đóng.

### 5.3 Reveal on scroll
`IntersectionObserver` (threshold 0.15) trên mọi phần tử `.reveal`:
- Trạng thái đầu: `opacity: 0; translateY(24px)`
- Khi vào viewport: thêm class `visible` → transition 0.9s ease về `opacity: 1; translateY(0)`, rồi unobserve
- Stagger: `transitionDelay = (index % 4) × 0.12s`
- Các phần tử `.reveal`: 3 dòng hero title, hero sub, hero actions

### 5.4 Hero canvas (đồ họa trang trí — KHÔNG phải data thật)
- Canvas full hero, scale theo `devicePixelRatio`, re-init khi resize
- **Lưới:** kẻ dọc + ngang mỗi 64px, màu `rgba(255,255,255,0.035)`
- **Nến giả:** số nến = `width / 18px`; sinh random-walk (drift `(rand−0.48) × H×0.03`, giá clamp trong dải 30%–75% chiều cao; wick hi/lo cộng random `H×0.015`)
- Màu: nến tăng `rgba(212,169,78, …)` (vàng) / giảm `rgba(120,133,151, …)` (xám xanh); wick alpha 0.5 width 1px, thân alpha 0.35 width 56% khoảng nến
- **Animation:** mỗi nến dập dềnh dọc `sin(t×0.6 + phase) × H×0.008`, loop `requestAnimationFrame`

---

## 6. CHECKLIST NỘI DUNG CHỜ ĐIỀN (placeholder)

- [ ] Tên công ty/team chính thức + logo (thay chữ "M" tạm)
- [ ] Giới thiệu chi tiết: lịch sử, tầm nhìn, sứ mệnh (§3.3)
- [ ] 4 con số stats: năm dữ liệu / thành viên / sản phẩm / đối tác (§3.3)
- [ ] Model Modus: hiệu suất công bố + trạng thái vận hành (§3.4)
- [ ] Sản phẩm 2, 3: tên + mô tả + spec (§3.4)
- [ ] Đội ngũ: họ tên, vị trí, ảnh chân dung ×4 (§3.6) + giới thiệu chung
- [ ] Trang/mục Tuyển dụng (nav dropdown)
- [ ] Logo đối tác 3 nhóm (§3.7)
- [ ] 3 bài viết insights: tiêu đề, ngày, thumbnail, link (§3.8)
- [ ] Hotline, email, địa chỉ văn phòng (§3.9)
- [ ] Tên pháp nhân trong copyright (§3.9)

---

## 7. GHI CHÚ MỞ RỘNG (gợi ý cho bản build ngoài)

- Cấu trúc hiện tại là 1 trang; khi có nội dung thật có thể tách route: `/about`, `/products/model-modus`, `/insights/*` — giữ nguyên design system §2
- Nếu dùng framework (Next.js/Astro/Vite): map mỗi section thành 1 component; design tokens §2.1–2.2 đưa vào theme config
- SEO nên thêm: Open Graph tags, favicon, sitemap.xml khi có domain
- Tuyệt đối không đưa số hiệu suất backtest chưa được duyệt lên trang công khai; giữ disclaimer §3.9 ở mọi trang

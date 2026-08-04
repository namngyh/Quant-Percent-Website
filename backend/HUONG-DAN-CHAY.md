# Hướng dẫn mở dự án Quant Percent

Dành cho người mới, không cần biết lập trình. Làm lần lượt từ trên xuống, **không bỏ bước**.

Dự án gồm 3 phần chạy cùng lúc:

```
Website (bạn nhìn thấy)  →  Backend (xử lý)  →  Database (chứa dữ liệu)
```

Phải bật đúng thứ tự: **Database → Backend → Website**.

Mọi lệnh trong tài liệu này gõ vào **PowerShell**. Mở PowerShell: bấm phím Windows, gõ `powershell`, bấm Enter.

---

# Phần 0 — Cài 4 phần mềm

Cài lần lượt, theo đúng thứ tự này:

| # | Phần mềm | Tải ở đâu | Lưu ý khi cài |
|---|---|---|---|
| 1 | **Git** | https://git-scm.com/download/win | Bấm Next hết, không cần đổi gì |
| 2 | **Docker Desktop** | https://www.docker.com/products/docker-desktop | Cài xong **phải mở app lên một lần** và đợi đến khi góc dưới bên trái hiện chữ xanh *Engine running* |
| 3 | **Node.js** | https://nodejs.org | Chọn bản ghi **LTS** |
| 4 | **Python** | https://www.python.org/downloads | Ở màn hình đầu tiên, **nhớ tick ô "Add python.exe to PATH"** rồi mới bấm Install |

Cài xong cả 4, **đóng hết cửa sổ PowerShell cũ và mở một cửa sổ mới**, rồi gõ:

```powershell
git --version; docker --version; node --version; python --version
```

**Đúng khi thấy:** 4 dòng, mỗi dòng có một con số phiên bản. Ví dụ:

```
git version 2.47.0
Docker version 29.6.2, build dfc4efb
v24.17.0
Python 3.14.5
```

Nếu có dòng nào báo *"not recognized"* nghĩa là phần mềm đó chưa cài xong hoặc chưa tick "Add to PATH" — cài lại phần mềm đó.

---

# Phần 1 — Tải mã nguồn

```powershell
mkdir D:\VuaBip123
cd D:\VuaBip123
```

```powershell
git clone https://github.com/tngkhanh/quantpercentBE.git
git clone https://github.com/tngkhanh/quantpercent.git
git clone https://github.com/MikeTyBo/Database-Onr-Percent.git
```

**Đúng khi thấy:** 3 thư mục xuất hiện trong `D:\VuaBip123`. Kiểm tra bằng `dir`.

> Repo thứ 3 (`Database-Onr-Percent`) nằm ở tài khoản GitHub khác. Nếu lệnh này báo lỗi
> *Repository not found* hoặc hỏi mật khẩu, nghĩa là bạn chưa được cấp quyền — **nhắn cho
> người quản lý dự án xin quyền truy cập**, không tự xử lý được.

---

# Phần 2 — Cài đặt lần đầu

Chỉ làm **một lần duy nhất**. Mất khoảng 20 phút, riêng bước 1 lần đầu hơi lâu vì phải tải dữ liệu về.

Trước khi bắt đầu: **mở app Docker Desktop**, đợi đến khi hiện *Engine running*.

### Bước 1 — Bật database

```powershell
cd "D:\Quant Percent\Database-Onr-Percent"
copy .env.example .env
notepad .env
```

Notepad vừa mở ra. Tìm và sửa **2 dòng** sau (giữ nguyên mọi dòng khác):

```
POSTGRES_PASSWORD=<dán một mật khẩu URL-safe ngẫu nhiên>
DATAPRO_MODE=mock
```

> Sinh mật khẩu bằng
> `python -c "import secrets; print(secrets.token_urlsafe(48))"`. Ghi lại,
> lát nữa cần dùng.

Bấm **Ctrl+S** để lưu, đóng Notepad. Quay lại PowerShell:

```powershell
docker compose up -d
```

Lần đầu chạy sẽ tải khoảng 300MB, đợi vài phút. Sau đó kiểm tra:

```powershell
docker compose ps
```

**Đúng khi thấy:** 3 dòng tên `qp-timescaledb`, `qp-redis`, `qp-ingestion`, cột STATUS có chữ `Up` hoặc `healthy`.

### Bước 2 — Tạo tài khoản database cho backend

```powershell
$env:QP_WEB_PASSWORD = python -c "import secrets; print(secrets.token_urlsafe(48))"
cd "D:\Quant Percent\Website QP\quantpercentBE"
Get-Content scripts\create_role.sql | docker exec -i qp-timescaledb psql -U quant -d market --set "api_password=$env:QP_WEB_PASSWORD"
```

> `$env:QP_WEB_PASSWORD` là mật khẩu riêng của backend, khác mật khẩu ở Bước
> 1. Ghi lại, Bước 3 cần dùng.

**Đúng khi thấy:** dòng cuối cùng là `Role qp_web ready. Now run: alembic upgrade head`

### Bước 3 — Tạo file cấu hình cho backend

```powershell
cd "D:\Quant Percent\Website QP\quantpercentBE"
copy .env.example .env
python -c "import secrets; print(secrets.token_urlsafe(64))" | Set-Clipboard
```

Lệnh thứ ba không in ra gì cả — bình thường. Nó vừa tạo một chuỗi mật khẩu ngẫu nhiên và **chép sẵn vào clipboard**, lát nữa chỉ cần bấm Ctrl+V để dán.

```powershell
notepad .env
```

Sửa **2 dòng** trong file vừa mở:

```
DATABASE_URL=postgresql+asyncpg://qp_web:<QP_WEB_PASSWORD>@localhost:5432/market
JWT_SECRET=
```

Ở dòng `JWT_SECRET=`, đặt con trỏ ngay sau dấu `=` rồi bấm **Ctrl+V** để dán chuỗi vừa tạo vào. Không có dấu cách, không có dấu nháy.

> Chỗ `<QP_WEB_PASSWORD>` phải đúng bằng mật khẩu ở Bước 2.

Ctrl+S để lưu, đóng Notepad.

### Bước 4 — Cài thư viện và tạo bảng trong database

```powershell
cd "D:\Quant Percent\Website QP\quantpercentBE"
python -m venv .venv
.venv\Scripts\python.exe -m pip install -r requirements-dev.txt
```

Lệnh thứ hai chạy khoảng 2–3 phút và in ra rất nhiều dòng chữ — bình thường.

**Đúng khi thấy:** dòng cuối bắt đầu bằng `Successfully installed`.

```powershell
$env:DATABASE_URL = "postgresql+asyncpg://quant:<POSTGRES_PASSWORD_B1>@localhost:5432/market"
.venv\Scripts\python.exe -m alembic upgrade head
Remove-Item Env:DATABASE_URL
```

Thay `<POSTGRES_PASSWORD_B1>` bằng mật khẩu ở Bước 1. Migration cần quyền
database owner; backend chạy thường xuyên vẫn dùng `qp_web` trong `.env`.
**Đúng khi thấy:** các dòng bắt đầu bằng `INFO  [alembic...]`, không có chữ `ERROR`.

### Bước 5 — Nạp danh sách model vào database

```powershell
cd D:\VuaBip123\quantpercentFE
npm install
npx tsx scripts/export-catalogue.ts
```

`npm install` chạy vài phút, in nhiều dòng — bình thường.

```powershell
cd D:\VuaBip123\quantpercentBE
.venv\Scripts\python.exe -m scripts.seed_catalogue --frontend ../quantpercentFE
```

**Đúng khi thấy:** đúng một dòng `seeded 12 models and 3 performance reports`

### Bước 6 — Nối website với backend

```powershell
cd D:\VuaBip123\quantpercent
notepad .env.local
```

Nếu Notepad hỏi *"Bạn có muốn tạo file mới không?"* → chọn **Yes**.

Gõ vào file đúng một dòng này:

```
NEXT_PUBLIC_API_BASE_URL=http://localhost:8000
```

Ctrl+S để lưu, đóng Notepad.

**Xong phần cài đặt.** Từ giờ chỉ cần làm Phần 3.

---

# Phần 3 — Mở dự án (làm mỗi ngày)

### 1. Bật Docker Desktop

Mở app **Docker Desktop**, đợi hiện *Engine running*. Database tự bật lại, không cần làm gì thêm.

Muốn chắc chắn, mở PowerShell gõ `docker ps` — phải thấy 3 dòng `qp-timescaledb`, `qp-redis`, `qp-ingestion`.

Nếu không thấy dòng nào:

```powershell
cd D:\VuaBip123\Database-Onr-Percent
docker compose up -d
```

### 2. Bật backend

Mở **cửa sổ PowerShell thứ nhất**:

```powershell
cd D:\VuaBip123\quantpercentBE
.venv\Scripts\python.exe -m uvicorn app.main:app --reload
```

**Đúng khi thấy:** `Uvicorn running on http://127.0.0.1:8000`

⚠️ **Để nguyên cửa sổ này, đừng đóng.** Đóng là backend tắt.

### 3. Bật website

Mở **cửa sổ PowerShell thứ hai**:

```powershell
cd D:\VuaBip123\quantpercent
npm run dev
```

**Đúng khi thấy:** `Ready in ...` kèm dòng `Local: http://localhost:3000`

⚠️ **Cũng để nguyên cửa sổ này.**

### 4. Mở trình duyệt

| Địa chỉ | Là gì |
|---|---|
| http://localhost:3000 | **Website — cái bạn cần xem** |
| http://localhost:8000/docs | Danh sách API, bấm thử được từng cái |
| http://localhost:8000/healthz | Kiểm tra backend sống chưa, phải hiện `{"status":"ok"}` |

---

# Phần 4 — Tắt khi làm xong

1. Ở **cả hai cửa sổ PowerShell**, bấm **Ctrl+C** rồi đóng cửa sổ.
2. Tắt database:

```powershell
cd D:\VuaBip123\Database-Onr-Percent
docker compose stop
```

> ⚠️ **Tuyệt đối không gõ `docker compose down -v`** — lệnh đó xoá sạch toàn bộ dữ liệu
> trong database, phải làm lại từ Bước 1.

---

# Phần 5 — Gặp lỗi thì làm gì

| Bạn nhìn thấy | Làm gì |
|---|---|
| `docker : The term 'docker' is not recognized` | Chưa cài Docker Desktop, hoặc cài xong chưa mở PowerShell mới. Mở cửa sổ PowerShell mới rồi thử lại |
| `error during connect` hoặc `cannot find the file specified` khi gõ lệnh docker | App Docker Desktop chưa chạy. Mở app, đợi hiện *Engine running*, thử lại |
| `password authentication failed for user "qp_web"` | Mật khẩu trong file `.env` của backend không khớp Bước 2. Làm lại **Bước 2 và Bước 3**, dùng cùng một mật khẩu ở cả hai chỗ |
| Website mở được nhưng số liệu trông giả / không đổi | File `.env.local` chưa đúng, hoặc chưa tắt bật lại website. Kiểm tra lại **Bước 6**, rồi Ctrl+C và chạy lại `npm run dev` |
| `Port 3000 is already in use` hoặc `address already in use` | Đang có cửa sổ khác chạy sẵn. Đóng hết cửa sổ PowerShell cũ rồi làm lại Phần 3 |
| `ModuleNotFoundError` hoặc `No module named ...` | Thiếu thư viện. Chạy lại lệnh `pip install` ở **Bước 4** |
| Trang Market Intelligence trống trơn | Bình thường — chưa có dữ liệu thị trường thật. Không phải lỗi |
| `429 Too Many Requests` khi đăng nhập | Đăng nhập sai quá 5 lần. Đợi 15 phút hoặc dùng email khác |

Lỗi khác, hoặc làm theo rồi vẫn không được: **chụp màn hình cả cửa sổ PowerShell** (thấy rõ dòng lệnh và dòng lỗi) rồi gửi cho người quản lý dự án.

---

Tài liệu chi tiết hơn dành cho người biết kỹ thuật: [README.md](./README.md).
Danh sách đầy đủ các API: [API.md](./API.md).

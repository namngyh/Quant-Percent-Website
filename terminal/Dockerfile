# QP Terminal cho production (terminal.quantpercent.com).
#
# Chạy uvicorn trực tiếp chứ không qua run.py: run.py tự bind thử cổng để kiểm
# tra trước và mở trình duyệt — cả hai đều vô nghĩa trong container.
#
# Dữ liệu (DuckDB + parquet trong data_store/) KHÔNG nằm trong image: compose
# gắn nó từ /srv/qp-terminal/data_store trên VPS, để tài khoản paper và nến đã
# backfill sống sót qua mỗi lần build lại.
#
# Bí mật (MARKET_DSN, TELEGRAM_*) đi vào qua biến môi trường (env_file trong
# compose), không phải file .env trong image. Lưu ý: lưu token Telegram từ giao
# diện vẫn có hiệu lực ngay, nhưng file .env nó ghi nằm trong container và mất
# khi build lại — muốn giữ lâu dài thì ghi vào /srv/qp-terminal/.env trên VPS.
FROM python:3.11-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1

WORKDIR /app

COPY requirements.txt .
RUN pip install -r requirements.txt

COPY . .

EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=5s --start-period=30s --retries=3 \
  CMD python -c "import urllib.request,sys; sys.exit(0 if urllib.request.urlopen('http://127.0.0.1:8000/api/live/status', timeout=3).status==200 else 1)"

CMD ["uvicorn", "backend.api.app:app", "--host", "0.0.0.0", "--port", "8000", \
     "--proxy-headers", "--forwarded-allow-ips=*"]

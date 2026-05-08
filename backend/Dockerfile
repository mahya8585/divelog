# プロジェクトルートからビルドすること
# docker build -f backend/Dockerfile -t divelog-backend .
# docker run -p 8000:8000 --env-file .env divelog-backend

FROM python:3.13-slim

WORKDIR /app

# 依存パッケージのみ先にコピーしてキャッシュを活用
COPY backend/requirements.txt ./requirements.txt
RUN pip install --no-cache-dir -r requirements.txt

# アプリケーションコードをコピー
COPY backend/ ./
COPY workflow/ ./workflow/

# 非 root ユーザーで実行
RUN useradd --uid 10001 --no-create-home --shell /usr/sbin/nologin appuser \
    && chown -R appuser:appuser /app
USER 10001

EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
  CMD python -c "import urllib.request, sys; \
urllib.request.urlopen('http://127.0.0.1:8000/health', timeout=3).read(); sys.exit(0)" || exit 1

# 本番: gunicorn / 開発: flask run
CMD ["gunicorn", "--bind", "0.0.0.0:8000", "--workers", "2", "--timeout", "60", "--forwarded-allow-ips", "*", "app:app"]

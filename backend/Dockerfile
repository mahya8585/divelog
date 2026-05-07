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

EXPOSE 8000

# 本番: gunicorn / 開発: flask run
CMD ["gunicorn", "--bind", "0.0.0.0:8000", "--workers", "2", "--timeout", "60", "app:app"]

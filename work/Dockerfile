FROM python:3.12-slim
WORKDIR /srv/kb
# 后端依赖（不含 PySide6：悬浮框是桌面客户端，不在容器内运行）
COPY requirements.txt .
RUN grep -viE '^(pyside6|markitdown|ranx|langchain)' requirements.txt > req-server.txt \
    && pip install --no-cache-dir -r req-server.txt fastembed==0.9.0
COPY app ./app
ENV DB_PATH=/data/kb.db PORT=8000
VOLUME /data
EXPOSE 8000
CMD ["sh", "-c", "uvicorn app.main:app --host 0.0.0.0 --port ${PORT}"]

FROM python:3.10-slim

# 设置工作目录
WORKDIR /app

# 安装依赖
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# 复制项目文件
COPY app.py .
COPY generate_session.py .

# 创建日志目录
RUN mkdir -p /app/logs

# 环境变量设置（这些是默认值，实际运行时应当被覆盖）
ENV TELEGRAM_API_ID=""
ENV TELEGRAM_API_HASH=""
ENV TELEGRAM_SESSION_STRING=""
ENV TELEGRAM_ADMIN_IDS=""
ENV TELEGRAM_SOURCE_CHAT_IDS=""
ENV TELEGRAM_TARGET_CHAT_IDS=""

# 定义数据卷
VOLUME ["/app/logs"]

# 启动命令
CMD ["python", "app.py"] 
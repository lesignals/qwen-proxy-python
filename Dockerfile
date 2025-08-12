# 使用官方Python runtime作为父镜像
FROM python:3.11-slim

# 设置工作目录
WORKDIR /app

# 安装系统依赖
RUN apt-get update && apt-get install -y \
    gcc \
    && rm -rf /var/lib/apt/lists/*

# 复制requirements.txt
COPY requirements.txt ./

# 安装Python依赖
RUN pip install --no-cache-dir -r requirements.txt

# 复制应用源码
COPY . ./

# 创建日志和数据目录
RUN mkdir -p /app/logs /app/data

# 设置非root用户
RUN addgroup --gid 1001 --system appuser
RUN adduser --uid 1001 --system --group appuser

# 更改目录权限
RUN chown -R appuser:appuser /app
USER appuser

# 暴露端口
EXPOSE 8080

# 健康检查
HEALTHCHECK --interval=30s --timeout=3s --start-period=5s --retries=3 \
  CMD python -c "import urllib.request; urllib.request.urlopen('http://localhost:8080/health'); exit(0)"

# 启动应用
CMD ["python", "main.py"]
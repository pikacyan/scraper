# Docker部署指南

本文档提供了使用Docker部署Telegram Pump监测机器人的详细指南。

## 准备工作

1. 确保已安装 [Docker](https://docs.docker.com/get-docker/) 和 [Docker Compose](https://docs.docker.com/compose/install/)
2. 获取Telegram API凭证（API ID和API Hash）
3. 生成session string（用于用户身份登录）

## 部署步骤

### 1. 创建目录结构

```bash
mkdir -p telegram-pump-bot/logs
cd telegram-pump-bot
```

### 2. 复制项目文件

将项目中的以下文件复制到当前目录：
- Dockerfile
- docker-compose.yml
- requirements.txt
- app.py
- generate_session.py
- env.example

### 3. 配置环境变量

程序现在完全使用环境变量进行配置：

1. 创建 `.env` 文件：
   ```bash
   cp env.example .env
   ```
2. 编辑 `.env` 文件，填入所有必需的环境变量：
   ```
   # Telegram API配置（必填）
   TELEGRAM_API_ID=your_api_id
   TELEGRAM_API_HASH=your_api_hash
   TELEGRAM_SESSION_STRING=your_session_string
   
   # Telegram聊天ID配置（必填）
   TELEGRAM_ADMIN_IDS=123456789,987654321
   TELEGRAM_SOURCE_CHAT_IDS=-1001234567890,-1009876543210
   TELEGRAM_TARGET_CHAT_IDS=-1001111222333,-1004445556667
   
   # 数据库配置（必填）
   POSTGRES_PASSWORD=your_secure_password
   POSTGRES_USER=postgres
   POSTGRES_DB=pumpbot
   POSTGRES_URL=postgresql://postgres:your_secure_password@db:5432/pumpbot
   ```

### 4. 生成Session String（如果还没有）

如果您还没有session string，可以在本地运行generate_session.py生成：

```bash
python generate_session.py
```

按照提示完成登录，然后将生成的session string复制到`.env`文件的`TELEGRAM_SESSION_STRING`变量中。

### 5. 启动服务

使用Docker Compose启动服务：

```bash
docker-compose up -d
```

首次启动时，系统会：
1. 构建Docker镜像
2. 创建PostgreSQL数据库
3. 启动机器人服务

### 6. 检查日志

查看机器人运行日志：

```bash
docker-compose logs -f pump-bot
```

## 管理服务

### 停止服务

```bash
docker-compose down
```

### 重启服务

```bash
docker-compose restart
```

### 更新配置

如需更改配置，请编辑`.env`文件，然后重启服务：

```bash
docker-compose restart pump-bot
```

## 持久化数据

所有数据都会持久化保存：
- 日志文件存储在 `./logs` 目录
- 数据库数据存储在Docker卷 `postgres-data` 中

## 所有环境变量说明

| 环境变量 | 说明 | 必填 |
|---------|------|------|
| TELEGRAM_API_ID | Telegram API ID | 是 |
| TELEGRAM_API_HASH | Telegram API Hash | 是 |
| TELEGRAM_SESSION_STRING | Telegram会话字符串 | 是 |
| TELEGRAM_ADMIN_IDS | 管理员用户ID，多个用逗号分隔 | 是 |
| TELEGRAM_SOURCE_CHAT_IDS | 源聊天ID，多个用逗号分隔 | 是 |
| TELEGRAM_TARGET_CHAT_IDS | 目标转发聊天ID，多个用逗号分隔 | 是 |
| POSTGRES_URL | PostgreSQL连接URL | 是 |
| POSTGRES_PASSWORD | PostgreSQL密码 | 是 |
| POSTGRES_USER | PostgreSQL用户名 | 是 |
| POSTGRES_DB | PostgreSQL数据库名 | 是 |

## 故障排除

1. 如果机器人无法启动，请检查日志：
   ```bash
   docker-compose logs pump-bot
   ```

2. 确保所有必要的环境变量已正确设置：
   - 检查`.env`文件是否存在并包含所有必要的变量
   - 检查Telegram API凭据是否正确
   - 确保session string有效

3. 数据库连接问题：
   - 确保PostgreSQL容器正在运行
   - 检查数据库连接URL是否正确
   - 可以尝试手动连接到数据库容器检查：
     ```bash
     docker-compose exec db psql -U postgres
     ```

4. Telegram连接问题：
   - 确保API ID和API Hash正确
   - 确保session string有效且未过期
   - 检查网络连接是否正常 
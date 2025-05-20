# Telegram Pump 监测机器人

这是一个用于监控和转发Telegram加密货币pump消息的机器人，可以根据等级筛选需要转发的消息。

## 功能特点

- 监控特定聊天中的pump消息
- 根据消息等级筛选 (Bad, Normal, Good, Excellent)
- 转发筛选后的消息到特定聊天
- 支持用户身份登录 (不仅限于Bot API)
- 持久保存设置到数据库

## 安装步骤

1. 克隆本项目
2. 安装所需依赖:
   ```
   pip install telethon asyncpg
   ```
3. 复制配置文件样本并进行编辑:
   ```
   cp config.ini.sample config.ini
   ```
   或使用提供的创建脚本:
   ```
   python create_config.py
   ```
4. 编辑 `config.ini` 文件，填入您的API信息和其他设置

## 用户身份登录

机器人支持两种登录方式:
1. 本地session文件登录 (默认)
2. 使用session string进行用户身份登录 (推荐)

### 生成Session String

要使用用户身份登录，首先需要生成一个session string:

1. 运行生成脚本:
   ```
   python generate_session.py
   ```
2. 根据提示输入您的API信息和登录验证信息
3. 脚本将生成session string并可选择自动更新配置文件

### 手动配置Session String

如果不想使用自动更新，您可以在生成session string后，手动将其添加到配置文件:

1. 打开 `config.ini` 文件
2. 在 `[telegram]` 部分找到 `session_string = `
3. 在等号后粘贴您的session string

## 运行机器人

配置完成后，运行以下命令启动机器人:

```
python app.py
```

## 命令列表

机器人支持以下命令:

- `/set [等级]` - 设置筛选等级（仅保存在内存中）
- `/set_and_save [等级]` - 设置筛选等级并保存到数据库
- `/status` - 查看当前设置状态
- `/help` - 显示帮助信息

## 等级说明

- `Bad` - 仅转发Bad及以上等级
- `Normal` - 仅转发Normal及以上等级
- `Good` - 仅转发Good及以上等级
- `Excellent` - 仅转发Excellent等级
- `All` - 转发所有消息，不筛选等级

## 数据库设置

机器人使用PostgreSQL数据库存储设置。支持两种数据库连接方式：

### 1. 使用连接URL字符串（推荐）

在 `config.ini` 中设置：

```ini
[database]
connection_url = postgresql://username:password@host:port/database
```

例如：
```ini
[database]
connection_url = postgresql://postgres:fziqovjr4an97tv2@web3-scraper-qecpnz:5432/postgres
```

### 2. 使用分离参数

```ini
[database]
host = localhost
port = 5432
user = postgres
password = your_password
database = pump_bot
```

注意：如果同时提供了连接URL和分离参数，会优先使用连接URL进行连接。 
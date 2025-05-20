# Telegram Solana 监测机器人 (Simple Version)

这是一个简化版的Telegram机器人，用于监控特定频道中包含Solana CA地址的消息，并将其转发到指定的聊天。

## 功能特点

- 监控特定聊天中的消息
- 自动识别Solana CA地址
- 转发包含CA地址的消息到指定聊天
- 支持用户身份登录 (通过session string)

## 安装步骤

1. 克隆本项目
2. 安装所需依赖:
   ```
   pip install -r requirements.txt
   ```
3. 复制环境变量示例并进行编辑:
   ```
   cp env.example .env
   ```
4. 编辑 `.env` 文件，填入您的API信息和其他设置

## 用户身份登录

使用session string进行用户身份登录:

### 生成Session String

要使用用户身份登录，首先需要生成一个session string:

1. 运行生成脚本:
   ```
   python generate_session.py
   ```
2. 根据提示输入您的API信息和登录验证信息
3. 获取生成的session string并添加到环境变量中

## 运行机器人

配置完成后，运行以下命令启动机器人:

```
python app.py
```

## Docker部署

1. 确保已安装Docker和Docker Compose
2. 复制环境变量文件:
   ```
   cp env.example .env
   ```
3. 编辑`.env`文件，填写所有必需参数
4. 使用Docker Compose启动服务:
   ```
   docker-compose up -d
   ```

## 命令列表

机器人支持以下命令:

- `/status` - 查看当前状态
- `/help` - 显示帮助信息 
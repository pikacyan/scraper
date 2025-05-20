import re
import os
import sys
import logging
import asyncio
from typing import Optional, List, Dict, Any

from telethon import TelegramClient, events
from telethon.sessions import StringSession

# 配置日志
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    handlers=[
        logging.FileHandler("bot.log", encoding="utf-8"),
        logging.StreamHandler(),
    ],
)
logger = logging.getLogger("solanabot")

class SolanaBot:
    def __init__(self):
        # 从环境变量中读取配置
        self.load_env_config()
        
        # 初始化Telegram客户端
        self.client = TelegramClient(
            StringSession(self.config["session_string"]),
            self.config["api_id"],
            self.config["api_hash"],
        )
        logger.info("正在使用session_string登录（用户模式）")
        
        # 注册事件处理器
        self.register_handlers()
    
    def load_env_config(self):
        """从环境变量加载配置"""
        self.config = {
            # Telegram 配置
            "api_id": os.environ.get("TELEGRAM_API_ID"),
            "api_hash": os.environ.get("TELEGRAM_API_HASH"),
            "session_string": os.environ.get("TELEGRAM_SESSION_STRING"),
            
            # 管理员用户ID列表
            "admin_ids": [int(id.strip()) for id in os.environ.get("TELEGRAM_ADMIN_IDS", "").split(",") if id.strip()],
            
            # 源聊天ID列表
            "source_chat_ids": [int(id.strip()) for id in os.environ.get("TELEGRAM_SOURCE_CHAT_IDS", "").split(",") if id.strip()],
            
            # 目标转发聊天ID列表
            "target_chat_ids": [int(id.strip()) for id in os.environ.get("TELEGRAM_TARGET_CHAT_IDS", "").split(",") if id.strip()],
        }
        
        # 验证必要配置是否存在
        missing_configs = []
        for key in ["api_id", "api_hash", "session_string"]:
            if not self.config.get(key):
                missing_configs.append(key)
        
        if missing_configs:
            logger.error(f"缺少必要的环境变量: {', '.join(missing_configs)}")
            sys.exit(1)
        
        # 验证列表配置
        if not self.config["admin_ids"]:
            logger.warning("未配置管理员ID，某些功能可能无法使用")
        
        if not self.config["source_chat_ids"]:
            logger.error("未配置源聊天ID，无法监听消息")
            sys.exit(1)
        
        if not self.config["target_chat_ids"]:
            logger.error("未配置目标聊天ID，无法转发消息")
            sys.exit(1)
            
        logger.info("从环境变量加载配置成功")
    
    def register_handlers(self):
        """注册消息处理器"""
        # 处理命令
        self.client.add_event_handler(
            self.handle_commands,
            events.NewMessage(pattern=r"^/(help|status)($|\s.*)"),
        )
        
        # 处理监听的消息
        for source_chat_id in self.config["source_chat_ids"]:
            self.client.add_event_handler(
                self.handle_solana_message,
                events.NewMessage(chats=source_chat_id, incoming=True),
            )
        
        logger.info("事件处理器注册成功")
    
    async def handle_commands(self, event):
        """处理命令消息"""
        sender = await event.get_sender()
        sender_id = sender.id
        
        # 检查发送者是否是管理员
        if sender_id not in self.config["admin_ids"]:
            await event.respond("⚠️ 您没有权限使用此命令")
            return
        
        command_parts = event.message.text.split()
        command = command_parts[0][1:]  # 去掉前缀/
        
        if command == "help":
            await self.handle_help_command(event)
        elif command == "status":
            await self.handle_status_command(event)
    
    async def handle_help_command(self, event):
        """处理help命令"""
        help_text = (
            "🤖 Solana监测机器人使用帮助:\n\n"
            "/status - 查看当前设置状态\n"
            "/help - 显示此帮助信息\n\n"
        )
        await event.respond(help_text)
    
    async def handle_status_command(self, event):
        """处理status命令"""
        status_text = f"机器人正在运行中\n监听源聊天: {len(self.config['source_chat_ids'])}个\n转发目标: {len(self.config['target_chat_ids'])}个"
        await event.respond(status_text)
    
    async def handle_solana_message(self, event):
        """处理接收到的Solana消息"""
        message_text = event.message.text
        
        # 尝试解析消息中的CA地址
        ca_addresses = self.extract_ca_addresses(message_text)
        
        if not ca_addresses:
            logger.debug("消息中未找到有效的Solana CA地址")
            return
        
        # 转发消息到目标聊天
        for chat_id in self.config["target_chat_ids"]:
            try:
                await self.client.forward_messages(chat_id, event.message)
                logger.info(f"已将包含CA地址 {ca_addresses} 的消息转发到聊天 {chat_id}")
            except Exception as e:
                logger.error(f"转发消息失败: {e}")
    
    def extract_ca_addresses(self, message_text: str) -> List[str]:
        """从消息中提取Solana CA地址"""
        # Solana地址通常是base58编码的44个字符
        # 简单的匹配模式: 查找以字母数字开头的43-44个字符的字符串
        solana_address_pattern = r'\b[1-9A-HJ-NP-Za-km-z]{43,44}\b'
        
        # 查找所有匹配项
        addresses = re.findall(solana_address_pattern, message_text)
        
        # 对查找到的地址进行进一步验证
        validated_addresses = []
        for addr in addresses:
            # 简单验证: Solana地址不包含 0, O, I, l
            if not any(c in addr for c in '0OIl'):
                validated_addresses.append(addr)
        
        return validated_addresses
    
    async def start(self):
        """启动机器人"""
        logger.info("开始初始化机器人...")
        
        # 启动Telethon客户端
        await self.client.start()
        me = await self.client.get_me()
        logger.info(f"已登录，用户: {me.first_name} (@{me.username if me.username else '无用户名'})")
        
        # 保持运行
        await self.client.run_until_disconnected()

async def main():
    """主函数"""
    # 检查必要的环境变量
    required_envs = ["TELEGRAM_API_ID", "TELEGRAM_API_HASH", "TELEGRAM_SESSION_STRING"]
    missing_envs = [env for env in required_envs if not os.environ.get(env)]
    
    if missing_envs:
        logger.error(f"缺少必要的环境变量: {', '.join(missing_envs)}")
        logger.error("请设置必要的环境变量后再启动程序")
        sys.exit(1)
    
    bot = SolanaBot()
    await bot.start()

if __name__ == "__main__":
    asyncio.run(main())

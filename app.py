import re
import os
import sys
import logging
import asyncio
import asyncpg
from typing import Optional, List, Dict, Any
import urllib.parse

from telethon import TelegramClient, events
from telethon.tl.types import User
from telethon.tl.functions.messages import GetHistoryRequest
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
logger = logging.getLogger("pumpbot")

# 定义等级枚举
LEVELS = ["Bad", "Normal", "Good", "Excellent", "All"]
DEFAULT_LEVEL = "Normal"  # 默认等级

class PumpBot:
    def __init__(self):
        # 初始化数据库连接池
        self.pool = None
        
        # 当前设置的筛选等级
        self.current_level = DEFAULT_LEVEL
        
        # 从环境变量中读取配置
        self.load_env_config()
        
        # 初始化Telegram客户端
        self.client = TelegramClient(
            StringSession(self.config["session_string"]),
            self.config["api_id"],
            self.config["api_hash"],
        )
        logger.info("正在使用环境变量中的session_string登录（用户模式）")
        
        # 注册事件处理器
        self.register_handlers()
    
    def load_env_config(self):
        """从环境变量加载配置"""
        self.config = {
            # Telegram 配置
            "api_id": os.environ.get("TELEGRAM_API_ID"),
            "api_hash": os.environ.get("TELEGRAM_API_HASH"),
            "session_string": os.environ.get("TELEGRAM_SESSION_STRING"),
            
            # 数据库配置
            "db_url": os.environ.get("POSTGRES_URL"),
            
            # 管理员用户ID列表
            "admin_ids": [int(id.strip()) for id in os.environ.get("TELEGRAM_ADMIN_IDS", "").split(",") if id.strip()],
            
            # 源聊天ID列表
            "source_chat_ids": [int(id.strip()) for id in os.environ.get("TELEGRAM_SOURCE_CHAT_IDS", "").split(",") if id.strip()],
            
            # 目标转发聊天ID列表
            "target_chat_ids": [int(id.strip()) for id in os.environ.get("TELEGRAM_TARGET_CHAT_IDS", "").split(",") if id.strip()],
        }
        
        # 验证必要配置是否存在
        missing_configs = []
        for key in ["api_id", "api_hash", "session_string", "db_url"]:
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
    
    async def init_db(self):
        """初始化数据库连接"""
        try:
            # 使用URL连接字符串
            self.pool = await asyncpg.create_pool(self.config["db_url"])
            logger.info("使用环境变量中的URL创建数据库连接池")
            
            # 创建表（如果不存在）
            async with self.pool.acquire() as conn:
                await conn.execute(
                    """
                    CREATE TABLE IF NOT EXISTS settings (
                        key TEXT PRIMARY KEY,
                        value TEXT
                    )
                    """
                )
            
            # 从数据库加载设置
            await self.load_settings_from_db()
            
            logger.info("数据库连接初始化成功")
        except Exception as e:
            logger.error(f"数据库连接失败: {e}")
            sys.exit(1)
    
    async def load_settings_from_db(self):
        """从数据库加载设置"""
        try:
            async with self.pool.acquire() as conn:
                # 获取保存的等级设置
                level_record = await conn.fetchrow(
                    "SELECT value FROM settings WHERE key = 'filter_level'"
                )
                
                if level_record:
                    saved_level = level_record["value"]
                    if saved_level in LEVELS:
                        self.current_level = saved_level
                        logger.info(f"从数据库加载等级设置: {self.current_level}")
                    else:
                        logger.warning(
                            f"数据库中的等级设置无效: {saved_level}，使用默认值: {DEFAULT_LEVEL}"
                        )
                else:
                    logger.info(f"数据库中未找到等级设置，使用默认值: {DEFAULT_LEVEL}")
        except Exception as e:
            logger.error(f"从数据库加载设置失败: {e}")
    
    async def save_settings_to_db(self):
        """保存设置到数据库"""
        try:
            async with self.pool.acquire() as conn:
                await conn.execute(
                    """
                    INSERT INTO settings (key, value) 
                    VALUES ('filter_level', $1)
                    ON CONFLICT (key) DO UPDATE
                    SET value = $1
                    """,
                    self.current_level,
                )
                logger.info(f"已将等级设置 {self.current_level} 保存到数据库")
        except Exception as e:
            logger.error(f"保存设置到数据库失败: {e}")
    
    def register_handlers(self):
        """注册消息处理器"""
        # 处理命令
        self.client.add_event_handler(
            self.handle_commands,
            events.NewMessage(pattern=r"^/(set|set_and_save|help|status)($|\s.*)"),
        )
        
        # 处理监听的消息
        for source_chat_id in self.config["source_chat_ids"]:
            self.client.add_event_handler(
                self.handle_pump_message,
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
        elif command in ["set", "set_and_save"]:
            if len(command_parts) < 2:
                await event.respond("❌ 请指定要设置的等级\n例如: /set Normal")
                return
            
            level = command_parts[1]
            await self.handle_set_command(
                event, level, save_to_db=(command == "set_and_save")
            )
        elif command == "status":
            await self.handle_status_command(event)
    
    async def handle_help_command(self, event):
        """处理help命令"""
        help_text = (
            "🤖 Pump监测机器人使用帮助:\n\n"
            "/set [等级] - 设置筛选等级（仅保存在内存中）\n"
            "/set_and_save [等级] - 设置筛选等级并保存到数据库\n"
            "/status - 查看当前设置状态\n"
            "/help - 显示此帮助信息\n\n"
            "可用等级: Bad, Normal, Good, Excellent, All\n"
            "等级说明:\n"
            "- Bad: 仅转发Bad及以上等级\n"
            "- Normal: 仅转发Normal及以上等级\n"
            "- Good: 仅转发Good及以上等级\n"
            "- Excellent: 仅转发Excellent等级\n"
            "- All: 转发所有消息，不筛选等级"
        )
        await event.respond(help_text)
    
    async def handle_set_command(self, event, level, save_to_db=False):
        """处理set和set_and_save命令"""
        if level not in LEVELS:
            await event.respond(
                f"❌ 无效的等级: {level}\n可用等级: {', '.join(LEVELS)}"
            )
            return
        
        self.current_level = level
        
        if save_to_db:
            await self.save_settings_to_db()
            await event.respond(f"✅ 已设置筛选等级为 {level} 并保存到数据库")
        else:
            await event.respond(f"✅ 已设置筛选等级为 {level}（仅保存在内存中）")
    
    async def handle_status_command(self, event):
        """处理status命令"""
        status_text = f"当前筛选等级: {self.current_level}"
        await event.respond(status_text)
    
    async def handle_pump_message(self, event):
        """处理接收到的pump消息"""
        message_text = event.message.text
        
        # 尝试解析消息
        pump_data = self.parse_pump_message(message_text)
        
        if not pump_data:
            logger.debug("收到的消息不是有效的pump消息")
            return
        
        # 检查消息等级是否符合筛选条件
        if not self.should_forward_by_level(pump_data):
            logger.info(
                f"消息等级不符合筛选条件: {pump_data.get('level', 'Unknown')}, 当前筛选等级: {self.current_level}"
            )
            return
        
        # 转发消息到目标聊天
        for chat_id in self.config["target_chat_ids"]:
            try:
                await self.client.forward_messages(chat_id, event.message)
                logger.info(
                    f"已将CA地址 {pump_data.get('ca_address', 'Unknown')} 的消息转发到聊天 {chat_id}"
                )
            except Exception as e:
                logger.error(f"转发消息失败: {e}")
    
    def parse_pump_message(self, message_text: str) -> Optional[Dict[str, Any]]:
        """解析pump消息，提取CA地址和等级等信息"""
        try:
            # 提取CA地址
            ca_match = re.search(r"🪙CA地址: ([^\s]+)", message_text)
            if not ca_match:
                return None
            
            ca_address = ca_match.group(1)
            
            # 提取等级信息
            level_match = re.search(r"等级: (\w+)", message_text)
            level = level_match.group(1) if level_match else "Unknown"
            
            # 提取其他可能需要的信息
            twitter_score_match = re.search(r"📊Twiiter评分: (\d+)分", message_text)
            twitter_score = (
                int(twitter_score_match.group(1)) if twitter_score_match else 0
            )
            
            current_market_value_match = re.search(
                r"💰当前市值: (\d+)\s*K", message_text
            )
            current_market_value = (
                int(current_market_value_match.group(1))
                if current_market_value_match
                else 0
            )
            
            followers_match = re.search(r"🙎粉丝数: (\d+)", message_text)
            followers = int(followers_match.group(1)) if followers_match else 0
            
            # 返回提取的信息
            return {
                "ca_address": ca_address,
                "level": level,
                "twitter_score": twitter_score,
                "current_market_value": current_market_value,
                "followers": followers,
                "raw_message": message_text,
            }
        except Exception as e:
            logger.error(f"解析消息失败: {e}")
            return None
    
    def should_forward_by_level(self, pump_data: Dict[str, Any]) -> bool:
        """根据等级决定是否应该转发消息"""
        # 如果设置为All，转发所有消息
        if self.current_level == "All":
            return True
        
        message_level = pump_data.get("level", "Unknown")
        
        # 等级优先级: Bad < Normal < Good < Excellent
        level_priority = {
            "Bad": 0,
            "Normal": 1,
            "Good": 2,
            "Excellent": 3,
            "Unknown": -1,  # 未知等级
        }
        
        # 如果消息中没有等级或等级无效，按照最低级别处理
        message_priority = level_priority.get(message_level, -1)
        current_priority = level_priority.get(self.current_level, 1)  # 默认为Normal
        
        # 消息等级优先级需要大于等于当前设置的过滤等级
        return message_priority >= current_priority
    
    async def start(self):
        """启动机器人"""
        logger.info("开始初始化机器人...")
        
        # 启动Telethon客户端
        await self.client.start()
        me = await self.client.get_me()
        logger.info(f"已登录，用户: {me.first_name} (@{me.username if me.username else '无用户名'})")
        
        # 初始化数据库连接
        await self.init_db()
        
        # 保持运行
        await self.client.run_until_disconnected()

async def main():
    """主函数"""
    # 检查必要的环境变量
    required_envs = ["TELEGRAM_API_ID", "TELEGRAM_API_HASH", "TELEGRAM_SESSION_STRING", "POSTGRES_URL"]
    missing_envs = [env for env in required_envs if not os.environ.get(env)]
    
    if missing_envs:
        logger.error(f"缺少必要的环境变量: {', '.join(missing_envs)}")
        logger.error("请设置必要的环境变量后再启动程序")
        sys.exit(1)
    
    bot = PumpBot()
    await bot.start()

if __name__ == "__main__":
    asyncio.run(main())

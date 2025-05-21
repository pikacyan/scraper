import re
import os
import sys
import logging
import asyncio
import asyncpg
from typing import Optional, List, Dict, Any, Set
import urllib.parse

from telethon import TelegramClient, events
from telethon.tl.types import User
from telethon.tl.functions.messages import GetHistoryRequest
from telethon.sessions import StringSession
from telethon.tl.types import PeerChannel, PeerChat, PeerUser


# 配置日志
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    handlers=[
        logging.FileHandler("bot.log", encoding="utf-8"),
        logging.StreamHandler(),
    ],
)
logger = logging.getLogger("VVVVVVVVVbot")

# 定义等级枚举
LEVELS = ["Bad", "Normal", "Good", "Excellent", "All"]
DEFAULT_LEVEL = "Normal"  # 默认等级


class VVVVVVVVVBot:
    def __init__(self):
        # 初始化数据库连接池
        self.pool = None

        # 当前设置的筛选等级
        self.current_level = DEFAULT_LEVEL

        # 内存存储的历史提取记录
        self.processed_ca_addresses = set()

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
            "admin_ids": [
                int(id.strip())
                for id in os.environ.get("TELEGRAM_ADMIN_IDS", "").split(",")
                if id.strip()
            ],
            # 源聊天ID列表
            "source_chat_ids": [
                int(id.strip())
                for id in os.environ.get("TELEGRAM_SOURCE_CHAT_IDS", "").split(",")
                if id.strip()
            ],
            # 目标转发聊天ID列表
            "target_chat_ids": [
                int(id.strip())
                for id in os.environ.get("TELEGRAM_TARGET_CHAT_IDS", "").split(",")
                if id.strip()
            ],
            # 监听的特定用户ID列表
            "watched_user_ids": [
                int(id.strip())
                for id in os.environ.get("TELEGRAM_WATCHED_USER_IDS", "").split(",")
                if id.strip()
            ],
            # 是否启用去重功能
            "enable_deduplication": os.environ.get(
                "ENABLE_DEDUPLICATION", "true"
            ).lower()
            == "true",
            # 内存中存储的最大CA地址数量
            "max_memory_addresses": int(os.environ.get("MAX_MEMORY_ADDRESSES", "1000")),
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

        if not self.config["watched_user_ids"]:
            logger.warning("未配置监听的用户ID，将监听群组中所有用户的消息")

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

                # 创建CA地址记录表
                await conn.execute(
                    """
                    CREATE TABLE IF NOT EXISTS ca_addresses (
                        address TEXT PRIMARY KEY,
                        level TEXT,
                        first_seen TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
                        twitter_score INTEGER DEFAULT 0,
                        market_value INTEGER DEFAULT 0,
                        followers INTEGER DEFAULT 0
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

                # 加载已处理的CA地址
                if self.config["enable_deduplication"]:
                    addresses = await conn.fetch(
                        "SELECT address FROM ca_addresses ORDER BY first_seen DESC LIMIT $1",
                        self.config["max_memory_addresses"],
                    )

                    for row in addresses:
                        self.processed_ca_addresses.add(row["address"])

                    logger.info(
                        f"从数据库加载了 {len(self.processed_ca_addresses)} 条CA地址记录"
                    )

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

    async def save_ca_address_to_db(self, ca_data):
        """保存CA地址到数据库"""
        try:
            if not self.pool:
                logger.warning("数据库连接池未初始化，无法保存CA地址")
                return

            async with self.pool.acquire() as conn:
                await conn.execute(
                    """
                    INSERT INTO ca_addresses (address, level, twitter_score, market_value, followers)
                    VALUES ($1, $2, $3, $4, $5)
                    ON CONFLICT (address) DO NOTHING
                    """,
                    ca_data.get("ca_address"),
                    ca_data.get("level", "Unknown"),
                    ca_data.get("twitter_score", 0),
                    ca_data.get("current_market_value", 0),
                    ca_data.get("followers", 0),
                )
                logger.info(f"已将CA地址 {ca_data.get('ca_address')} 保存到数据库")
        except Exception as e:
            logger.error(f"保存CA地址到数据库失败: {e}")

    def register_handlers(self):
        """注册消息处理器"""
        # 处理命令
        self.client.add_event_handler(
            self.handle_commands,
            events.NewMessage(
                pattern=r"^/(set|set_and_save|clear|help|status)($|\s.*)"
            ),
        )

        # 打印配置信息以便调试
        logger.info(f"监听的群组IDs: {self.config['source_chat_ids']}")
        logger.info(f"目标转发群组/用户IDs: {self.config['target_chat_ids']}")
        logger.info(f"监听的特定用户IDs: {self.config['watched_user_ids']}")

        # 处理监听的消息
        # 1. 如果配置了要监听的特定用户，则监听这些用户在特定群组发送的消息
        if self.config["watched_user_ids"]:
            for source_chat_id in self.config["source_chat_ids"]:
                for user_id in self.config["watched_user_ids"]:
                    logger.info(
                        f"注册监听: 用户 {user_id} 在群组 {source_chat_id} 的消息"
                    )
                    self.client.add_event_handler(
                        self.handle_VVVVVVVVV_message,
                        events.NewMessage(chats=source_chat_id, from_users=user_id),
                    )
        else:
            # 2. 如果没有配置特定用户，则监听群组中的所有消息
            for source_chat_id in self.config["source_chat_ids"]:
                logger.info(f"注册监听: 群组 {source_chat_id} 的所有消息")
                self.client.add_event_handler(
                    self.handle_VVVVVVVVV_message,
                    events.NewMessage(chats=source_chat_id),
                )

        # 3. 添加处理转发消息的处理器
        for source_chat_id in self.config["source_chat_ids"]:
            logger.info(f"注册监听: 群组 {source_chat_id} 的所有转发消息")
            self.client.add_event_handler(
                self.handle_forwarded_message,
                events.NewMessage(chats=source_chat_id),
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
        elif command == "clear":
            await self.handle_clear_command(event)

    async def handle_help_command(self, event):
        """处理help命令"""
        help_text = (
            "🤖 VVVVVVVVV监测机器人使用帮助:\n\n"
            "/set [等级] - 设置筛选等级（仅保存在内存中）\n"
            "/set_and_save [等级] - 设置筛选等级并保存到数据库\n"
            "/clear - 清空内存中存储的CA地址记录\n"
            "/status - 查看当前设置状态\n"
            "/help - 显示此帮助信息\n\n"
            "可用等级: Bad, Normal, Good, Excellent, All\n"
            "等级说明:\n"
            "- Bad: 仅处理Bad及以上等级\n"
            "- Normal: 仅处理Normal及以上等级\n"
            "- Good: 仅处理Good及以上等级\n"
            "- Excellent: 仅处理Excellent等级\n"
            "- All: 处理所有消息，不筛选等级\n\n"
            "机器人现在监听特定用户发送的消息，并将提取到的CA地址发送给目标用户"
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
        # 获取当前登录账号信息
        me = await self.client.get_me()
        is_bot = getattr(me, "bot", False)
        account_type = "机器人" if is_bot else "用户账号"

        status_text = (
            f"📊 当前状态信息\n\n"
            f"👤 登录账号: {me.first_name} (@{me.username if me.username else '无用户名'})\n"
            f"📱 账号类型: {account_type}\n"
            f"🔍 当前筛选等级: {self.current_level}\n\n"
            f"🔢 统计信息\n"
            f"- 内存中存储的CA地址数量: {len(self.processed_ca_addresses)}\n\n"
            f"🎯 目标接收者: {len(self.config['target_chat_ids'])}个\n"
            f"📡 监听的群组: {len(self.config['source_chat_ids'])}个\n"
            f"👥 监听的特定用户: {len(self.config['watched_user_ids'])}个\n\n"
            f"⚙️ 功能设置\n"
            f"- 去重功能: {'已启用' if self.config['enable_deduplication'] else '已禁用'}\n"
            f"- 最大内存存储地址数: {self.config['max_memory_addresses']}"
        )
        await event.respond(status_text)

    async def handle_clear_command(self, event):
        """处理clear命令，清空内存中的CA地址记录"""
        old_count = len(self.processed_ca_addresses)
        self.processed_ca_addresses.clear()
        await event.respond(f"✅ 已清空内存中的CA地址记录，共清除 {old_count} 条记录")

    async def handle_VVVVVVVVV_message(self, event):
        """处理接收到的VVVVVVVVV消息"""
        # 打印详细的事件信息，帮助调试
        logger.info(f"收到消息 event ID: {event.id}")

        # 获取消息来源的详细信息
        sender = await event.get_sender()
        sender_id = sender.id
        chat = await event.get_chat()
        chat_id = chat.id

        # 打印消息来源细节
        logger.info(
            f"消息来源 - 发送者ID: {sender_id}, 姓名: {sender.first_name}, 用户名: {getattr(sender, 'username', '无')}"
        )
        logger.info(
            f"消息来源 - 聊天ID: {chat_id}, 聊天标题: {getattr(chat, 'title', '私聊')}"
        )

        # 如果配置了要监听的特定用户，则只处理这些用户的消息
        if (
            self.config["watched_user_ids"]
            and sender_id not in self.config["watched_user_ids"]
        ):
            logger.debug(f"忽略非监听用户 {sender_id} 的消息")
            return

        message_text = event.message.text
        logger.info(f"消息内容: {message_text[:200]}...")  # 限制长度避免日志过大

        # 尝试解析消息
        VVVVVVVVV_data = self.parse_VVVVVVVVV_message(message_text)

        if not VVVVVVVVV_data:
            logger.debug("收到的消息不是有效的VVVVVVVVV消息")
            return

        # 检查消息等级是否符合筛选条件
        if not self.should_forward_by_level(VVVVVVVVV_data):
            logger.info(
                f"消息等级不符合筛选条件: {VVVVVVVVV_data.get('level', 'Unknown')}, 当前筛选等级: {self.current_level}"
            )
            return

        # 提取CA地址
        ca_address = VVVVVVVVV_data.get("ca_address", None)
        if not ca_address:
            logger.error("无法从消息中提取CA地址")
            return

        # 如果启用了去重功能，检查是否已经处理过该CA地址
        if (
            self.config["enable_deduplication"]
            and ca_address in self.processed_ca_addresses
        ):
            logger.info(f"CA地址 {ca_address} 已经处理过，跳过")
            return

        # 将CA地址添加到已处理集合中
        self.processed_ca_addresses.add(ca_address)

        # 如果超过最大存储数量，移除最早的记录
        if len(self.processed_ca_addresses) > self.config["max_memory_addresses"]:
            # 移除一个元素（由于set无序，这里只能随机移除）
            self.processed_ca_addresses.pop()

        # 保存CA地址到数据库
        await self.save_ca_address_to_db(VVVVVVVVV_data)

        # 准备发送的消息 - 仅发送CA地址
        send_text = ca_address

        # 发送消息到目标聊天
        for chat_id in self.config["target_chat_ids"]:
            try:
                await self.send_message_to_target(chat_id, send_text, ca_address)
            except Exception as e:
                logger.error(f"发送消息失败: {e}")

    async def handle_forwarded_message(self, event):
        """处理转发的消息"""
        # 检查是否是转发消息
        if not event.forward:
            return

        logger.info(f"检测到转发消息: {event.id}")

        # 打印转发的详细信息
        if hasattr(event.forward, "sender_id"):
            forward_sender_id = event.forward.sender_id
            logger.info(f"转发消息的原发送者ID: {forward_sender_id}")

            # 如果配置了监听特定用户，检查转发的原发送者是否在监听列表中
            if (
                self.config["watched_user_ids"]
                and forward_sender_id not in self.config["watched_user_ids"]
            ):
                logger.debug(f"忽略非监听用户 {forward_sender_id} 的转发消息")
                return

            # 获取消息来源的详细信息
            chat = await event.get_chat()
            chat_id = chat.id

            # 打印消息来源细节
            logger.info(
                f"转发消息来源 - 聊天ID: {chat_id}, 聊天标题: {getattr(chat, 'title', '私聊')}"
            )

            # 处理转发的消息内容
            message_text = event.message.text
            logger.info(
                f"转发消息内容: {message_text[:200]}..."
            )  # 限制长度避免日志过大

            # 使用与handle_VVVVVVVVV_message相同的逻辑处理消息内容
            # 尝试解析消息
            VVVVVVVVV_data = self.parse_VVVVVVVVV_message(message_text)

            if not VVVVVVVVV_data:
                logger.debug("收到的转发消息不是有效的VVVVVVVVV消息")
                return

            # 检查消息等级是否符合筛选条件
            if not self.should_forward_by_level(VVVVVVVVV_data):
                logger.info(
                    f"转发消息等级不符合筛选条件: {VVVVVVVVV_data.get('level', 'Unknown')}, 当前筛选等级: {self.current_level}"
                )
                return

            # 提取CA地址
            ca_address = VVVVVVVVV_data.get("ca_address", None)
            if not ca_address:
                logger.error("无法从转发消息中提取CA地址")
                return

            # 如果启用了去重功能，检查是否已经处理过该CA地址
            if (
                self.config["enable_deduplication"]
                and ca_address in self.processed_ca_addresses
            ):
                logger.info(f"CA地址 {ca_address} 已经处理过，跳过")
                return

            # 将CA地址添加到已处理集合中
            self.processed_ca_addresses.add(ca_address)

            # 如果超过最大存储数量，移除最早的记录
            if len(self.processed_ca_addresses) > self.config["max_memory_addresses"]:
                # 移除一个元素（由于set无序，这里只能随机移除）
                self.processed_ca_addresses.pop()

            # 保存CA地址到数据库
            await self.save_ca_address_to_db(VVVVVVVVV_data)

            # 准备发送的消息 - 仅发送CA地址
            send_text = ca_address

            # 发送消息到目标聊天
            for chat_id in self.config["target_chat_ids"]:
                try:
                    await self.send_message_to_target(chat_id, send_text, ca_address)
                except Exception as e:
                    logger.error(f"发送转发消息失败: {e}")
        else:
            logger.info("转发消息没有发送者ID信息")

    async def send_message_to_target(
        self, target_chat_id, message_text, ca_address=None
    ):
        """发送消息到目标聊天，包含实体解析处理"""
        try:
            logger.info(f"正在尝试向 {target_chat_id} 发送消息...")

            # 获取自身信息，判断是否为用户账号
            me = await self.client.get_me()
            is_bot = getattr(me, "bot", False)

            # 记录详细信息以便调试
            logger.info(f"当前登录账号: {'机器人' if is_bot else '用户账号'}")
            logger.info(f"目标ID类型: {type(target_chat_id)}, 值: {target_chat_id}")

            # 尝试直接获取目标实体
            try:
                logger.info(f"尝试获取目标 {target_chat_id} 的实体...")
                entity = await self.client.get_entity(target_chat_id)
                logger.info(f"成功获取实体: {type(entity).__name__} - {entity}")

                # 发送消息
                await self.client.send_message(entity, message_text)
                if ca_address:
                    logger.info(f"已将CA地址 {ca_address} 发送到 {target_chat_id}")
                else:
                    logger.info(f"已发送消息到 {target_chat_id}")
                return True

            except ValueError as e:
                logger.warning(f"无法获取实体: {e}")

                # 如果是数字ID，尝试不同的方式构造实体
                if isinstance(target_chat_id, int):
                    logger.info(f"尝试使用数字ID构造实体...")

                    # 尝试获取对话历史
                    try:
                        logger.info("尝试通过获取对话历史来获取实体...")
                        # 获取最近的对话列表
                        dialogs = await self.client.get_dialogs(limit=50)
                        for dialog in dialogs:
                            if (
                                hasattr(dialog.entity, "id")
                                and dialog.entity.id == target_chat_id
                            ):
                                logger.info(
                                    f"在对话历史中找到匹配实体: {dialog.entity}"
                                )

                                # 使用对话实体发送消息
                                await self.client.send_message(
                                    dialog.entity, message_text
                                )
                                if ca_address:
                                    logger.info(
                                        f"已将CA地址 {ca_address} 发送到 {target_chat_id}"
                                    )
                                else:
                                    logger.info(f"已发送消息到 {target_chat_id}")
                                return True

                        logger.warning(
                            f"在对话历史中未找到ID为 {target_chat_id} 的实体"
                        )
                    except Exception as hist_err:
                        logger.warning(f"获取对话历史失败: {hist_err}")

                logger.error(
                    f"所有尝试都失败，无法获取ID为 {target_chat_id} 的有效实体"
                )
                raise ValueError(f"无法获取有效实体: {target_chat_id}")

            except Exception as e:
                logger.error(f"获取实体时遇到未知错误: {e}")
                raise

        except Exception as e:
            error_msg = str(e).lower()

            # 提供详细的错误信息
            if "bot" in error_msg and (
                "conversation" in error_msg or "peer" in error_msg
            ):
                logger.error(
                    f"Telegram API限制: 机器人无法主动与用户 {target_chat_id} 开始对话"
                )
                logger.error(
                    f"解决方法: 1.用户必须先向机器人发送消息 2.或将消息发送到机器人已加入的群组"
                )
            else:
                logger.error(f"发送消息失败: {e}")
                logger.error(
                    f"无法发送消息到 {target_chat_id}，请确保已与该用户/群组有过交互"
                )

            return False

    def parse_VVVVVVVVV_message(self, message_text: str) -> Optional[Dict[str, Any]]:
        """解析VVVVVVVVV消息，提取CA地址和等级等信息"""
        try:
            # 打印原始消息文本，用于调试
            logger.info(
                f"开始解析消息: {message_text[:200]}..."
            )  # 限制长度避免日志过大

            # 尝试多种CA地址匹配模式
            ca_patterns = [
                r"🪙CA地址: ([^\s]+)",
                r"🪙\s*CA地址\s*:\s*([^\s]+)",
                r"CA地址\s*:\s*([^\s]+)",
                r"CA地址:\s*([^\s]+)",
                r"CA\s*:\s*([^\s]+)",
                r"CA:([^\s]+)",
                r"([a-zA-Z0-9]{40,42})",  # 尝试直接匹配CA地址格式
            ]

            ca_address = None
            for pattern in ca_patterns:
                ca_match = re.search(pattern, message_text)
                if ca_match:
                    ca_address = ca_match.group(1)
                    logger.info(f"匹配到CA地址: {ca_address}，使用模式: {pattern}")
                    break

            if not ca_address:
                logger.info("未能匹配到CA地址")
                return None

            # 尝试多种等级匹配模式
            level_patterns = [
                r"等级: (\w+)",
                r"等级\s*:\s*(\w+)",
                r"level\s*:\s*(\w+)",
                r"Level\s*:\s*(\w+)",
            ]

            level = "Unknown"
            for pattern in level_patterns:
                level_match = re.search(pattern, message_text)
                if level_match:
                    level = level_match.group(1)
                    logger.info(f"匹配到等级: {level}，使用模式: {pattern}")
                    break

            # 如果没有找到明确的等级，尝试从消息内容推断
            if level == "Unknown":
                if "excellent" in message_text.lower():
                    level = "Excellent"
                elif "good" in message_text.lower():
                    level = "Good"
                elif "normal" in message_text.lower():
                    level = "Normal"
                elif "bad" in message_text.lower():
                    level = "Bad"
                logger.info(f"从消息内容推断等级: {level}")

            # 提取其他可能需要的信息
            twitter_score_patterns = [
                r"📊Twiiter评分: (\d+)分",
                r"Twiiter评分: (\d+)",
                r"Twitter评分: (\d+)",
                r"推特评分: (\d+)",
            ]

            twitter_score = 0
            for pattern in twitter_score_patterns:
                twitter_score_match = re.search(pattern, message_text)
                if twitter_score_match:
                    twitter_score = int(twitter_score_match.group(1))
                    logger.info(
                        f"匹配到Twitter评分: {twitter_score}，使用模式: {pattern}"
                    )
                    break

            market_value_patterns = [
                r"💰当前市值: (\d+)\s*K",
                r"当前市值: (\d+)",
                r"市值: (\d+)",
            ]

            current_market_value = 0
            for pattern in market_value_patterns:
                market_match = re.search(pattern, message_text)
                if market_match:
                    current_market_value = int(market_match.group(1))
                    logger.info(
                        f"匹配到当前市值: {current_market_value}，使用模式: {pattern}"
                    )
                    break

            followers_patterns = [
                r"🙎粉丝数: (\d+)",
                r"粉丝数: (\d+)",
                r"followers: (\d+)",
                r"Followers: (\d+)",
            ]

            followers = 0
            for pattern in followers_patterns:
                followers_match = re.search(pattern, message_text)
                if followers_match:
                    followers = int(followers_match.group(1))
                    logger.info(f"匹配到粉丝数: {followers}，使用模式: {pattern}")
                    break

            # 返回提取的信息
            result = {
                "ca_address": ca_address,
                "level": level,
                "twitter_score": twitter_score,
                "current_market_value": current_market_value,
                "followers": followers,
                "raw_message": message_text,
            }

            logger.info(f"解析结果: {result}")
            return result
        except Exception as e:
            logger.error(f"解析消息失败: {e}")
            return None

    def should_forward_by_level(self, VVVVVVVVV_data: Dict[str, Any]) -> bool:
        """根据等级决定是否应该处理消息"""
        # 如果设置为All，处理所有消息
        if self.current_level == "All":
            return True

        message_level = VVVVVVVVV_data.get("level", "Unknown")

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
        logger.info(
            f"已登录，用户: {me.first_name} (@{me.username if me.username else '无用户名'})"
        )

        # 检查客户端是否是机器人
        is_bot = getattr(me, "bot", False)
        logger.info(f"当前客户端{'是' if is_bot else '不是'}机器人")

        # 如果是用户账号，可以向自己发送消息作为测试/备用方案
        if not is_bot:
            logger.info(f"检测到用户账号登录，可以向自己发送消息作为测试")
            self_chat_id = me.id
            logger.info(f"自己的用户ID为: {self_chat_id}")

        # 初始化数据库连接
        await self.init_db()

        # 尝试获取所有目标聊天的实体
        logger.info("尝试获取所有目标聊天的实体...")
        for chat_id in self.config["target_chat_ids"]:
            try:
                entity = await self.client.get_entity(chat_id)
                logger.info(f"成功获取目标聊天实体: {entity}")
            except Exception as e:
                logger.warning(f"无法获取聊天ID {chat_id} 的实体: {e}")
                logger.warning(
                    f"这可能导致无法向该聊天发送消息。请确保已与该用户/群组有过交互"
                )

        # 尝试获取所有监听群组的实体
        logger.info("尝试获取所有监听群组的实体...")
        for chat_id in self.config["source_chat_ids"]:
            try:
                entity = await self.client.get_entity(chat_id)
                logger.info(f"成功获取监听群组实体: {entity}")
            except Exception as e:
                logger.error(f"无法获取聊天ID {chat_id} 的实体: {e}")
                logger.error(f"这将导致无法监听该群组的消息。请确保机器人已加入该群组")

        # 保持运行
        await self.client.run_until_disconnected()


async def main():
    """主函数"""
    # 检查必要的环境变量
    required_envs = [
        "TELEGRAM_API_ID",
        "TELEGRAM_API_HASH",
        "TELEGRAM_SESSION_STRING",
        "POSTGRES_URL",
    ]
    missing_envs = [env for env in required_envs if not os.environ.get(env)]

    if missing_envs:
        logger.error(f"缺少必要的环境变量: {', '.join(missing_envs)}")
        logger.error("请设置必要的环境变量后再启动程序")
        sys.exit(1)

    bot = VVVVVVVVVBot()
    await bot.start()


if __name__ == "__main__":
    asyncio.run(main())

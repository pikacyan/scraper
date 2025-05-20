import asyncio
import sys
import os
import configparser
from telethon import TelegramClient
from telethon.sessions import StringSession

async def generate_session_string():
    """生成Telegram用户会话字符串(session string)"""
    
    # 检查是否存在配置文件
    config_file = "config.ini"
    config = configparser.ConfigParser()
    
    # 尝试从配置文件读取API ID和API Hash
    api_id = None
    api_hash = None
    
    if os.path.exists(config_file):
        # 使用UTF-8编码读取配置文件
        with open(config_file, 'r', encoding='utf-8') as f:
            config.read_file(f)
        
        if 'telegram' in config and 'api_id' in config['telegram'] and 'api_hash' in config['telegram']:
            api_id = config['telegram']['api_id']
            api_hash = config['telegram']['api_hash']
            print(f"已从配置文件中读取API ID和API Hash")
    
    # 如果配置文件中没有API ID和API Hash，则从用户输入获取
    if not api_id or not api_hash:
        print("请输入Telegram API信息 (获取地址: https://my.telegram.org/apps)")
        api_id = input("API ID: ")
        api_hash = input("API Hash: ")
    
    # 创建Telethon客户端
    client = TelegramClient(StringSession(), api_id, api_hash)
    
    try:
        # 启动客户端并登录
        print("\n正在启动Telegram客户端...")
        await client.start()
        
        # 检查是否已登录
        if not await client.is_user_authorized():
            print("\n您需要登录您的Telegram账号，请按照以下步骤操作:")
            print("1. 输入您的手机号码（包含国家代码，例如：+86xxxxxxxxxxx）")
            phone = input("电话号码: ")
            
            # 发送验证码
            await client.send_code_request(phone)
            
            # 输入验证码
            print("\n2. 输入您收到的验证码")
            code = input("验证码: ")
            
            try:
                await client.sign_in(phone, code)
            except Exception as e:
                if "2FA" in str(e) or "PASSWORD_HASH_INVALID" in str(e):
                    # 需要输入两步验证密码
                    print("\n您的账号启用了两步验证，需要输入密码")
                    password = input("两步验证密码: ")
                    await client.sign_in(password=password)
                else:
                    raise e
        
        # 获取登录的用户信息
        me = await client.get_me()
        print(f"\n成功登录! 账号: {me.first_name} (@{me.username if me.username else '无用户名'})")
        
        # 获取session string
        session_string = client.session.save()
        print("\n生成的Session String (请妥善保管，不要泄露给他人):")
        print("-" * 50)
        print(session_string)
        print("-" * 50)
        
        # 提示如何使用
        print("\n使用说明:")
        print("1. 将此session_string添加到config.ini文件的[telegram]部分")
        print("2. 添加格式: session_string = " + session_string)
        
        # 如果配置文件存在，询问是否自动更新
        if os.path.exists(config_file):
            update = input("\n是否自动更新配置文件? (y/n): ")
            if update.lower() == 'y':
                if 'telegram' not in config:
                    config['telegram'] = {}
                config['telegram']['session_string'] = session_string
                # 使用UTF-8编码写入配置文件
                with open(config_file, 'w', encoding='utf-8') as f:
                    config.write(f)
                print(f"已更新配置文件 {config_file}")
    
    except Exception as e:
        print(f"出错了: {e}")
    finally:
        await client.disconnect()

if __name__ == "__main__":
    asyncio.run(generate_session_string()) 
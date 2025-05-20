import os
import shutil
import configparser

def create_config_file():
    """创建配置文件，确保UTF-8编码"""
    sample_file = "config.ini.sample"
    config_file = "config.ini"
    
    # 检查样本文件是否存在
    if not os.path.exists(sample_file):
        print(f"错误: 样本配置文件 {sample_file} 不存在!")
        return False
    
    # 如果配置文件已存在，询问是否覆盖
    if os.path.exists(config_file):
        overwrite = input(f"配置文件 {config_file} 已存在，是否覆盖? (y/n): ")
        if overwrite.lower() != 'y':
            print("操作已取消")
            return False
    
    # 从样本文件创建配置
    config = configparser.ConfigParser()
    
    try:
        # 读取样本文件
        with open(sample_file, 'r', encoding='utf-8') as f:
            config.read_file(f)
        
        # 写入新的配置文件
        with open(config_file, 'w', encoding='utf-8') as f:
            config.write(f)
        
        print(f"成功创建配置文件 {config_file}")
        print("请编辑此文件，填入您的Telegram API信息和其他设置")
        return True
    
    except Exception as e:
        print(f"创建配置文件时出错: {e}")
        return False

if __name__ == "__main__":
    create_config_file() 
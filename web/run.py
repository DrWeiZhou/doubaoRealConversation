#!/usr/bin/env python3
"""
豆包语音对话系统 - Web应用启动脚本
"""

import uvicorn
import os
import sys
import logging
from pathlib import Path

# 配置启动日志
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s [%(levelname)s] %(name)s: %(message)s',
    datefmt='%Y-%m-%d %H:%M:%S'
)
logger = logging.getLogger(__name__)

def main():
    """启动FastAPI应用"""
    
    # 检查是否在web目录下运行
    current_dir = Path.cwd()
    if current_dir.name != 'web':
        web_dir = current_dir / 'web'
        if web_dir.exists():
            os.chdir(web_dir)
            logger.info(f"切换到web目录: {web_dir}")
            print(f"切换到web目录: {web_dir}")
        else:
            logger.error("错误：请在web目录下运行此脚本")
            print("错误：请在web目录下运行此脚本")
            sys.exit(1)
    
    # 启动服务器
    logger.info("正在启动豆包语音对话系统...")
    print("🎤 正在启动豆包语音对话系统...")
    print("📱 打开浏览器访问: http://localhost:8000")
    print("🔗 WebSocket端点: ws://localhost:8000/ws")
    print("🛑 按 Ctrl+C 停止服务")
    print("📄 日志文件: doubao_web.log")
    
    try:
        uvicorn.run(
            "app:app",
            host="0.0.0.0",
            port=8000,
            reload=True,
            log_level="info",
            access_log=True
        )
    except KeyboardInterrupt:
        logger.info("服务被用户停止")
        print("\n👋 服务已停止")
    except Exception as e:
        logger.error(f"服务启动失败: {e}")
        print(f"\n❌ 服务启动失败: {e}")

if __name__ == "__main__":
    main()
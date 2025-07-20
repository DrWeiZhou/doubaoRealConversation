#!/usr/bin/env python3
"""
豆包语音对话系统 - Web应用启动脚本
"""

import uvicorn
import os
import sys
from pathlib import Path

def main():
    """启动FastAPI应用"""
    
    # 检查是否在web目录下运行
    current_dir = Path.cwd()
    if current_dir.name != 'web':
        web_dir = current_dir / 'web'
        if web_dir.exists():
            os.chdir(web_dir)
            print(f"切换到web目录: {web_dir}")
        else:
            print("错误：请在web目录下运行此脚本")
            sys.exit(1)
    
    # 启动服务器
    print("🎤 正在启动豆包语音对话系统...")
    print("📱 打开浏览器访问: http://localhost:8000")
    print("🔗 WebSocket端点: ws://localhost:8000/ws")
    print("🛑 按 Ctrl+C 停止服务")
    
    try:
        uvicorn.run(
            "app:app",
            host="0.0.0.0",
            port=8000,
            reload=True,
            log_level="info"
        )
    except KeyboardInterrupt:
        print("\n👋 服务已停止")

if __name__ == "__main__":
    main()
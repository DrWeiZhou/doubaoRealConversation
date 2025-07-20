import os
import sys
import asyncio
import json
import base64
import logging
from pathlib import Path
from typing import Dict, Any

from fastapi import FastAPI, WebSocket, WebSocketDisconnect, HTTPException
from fastapi.staticfiles import StaticFiles
from fastapi.responses import HTMLResponse, FileResponse
from pydantic import BaseModel
from dotenv import load_dotenv

# 添加父目录到路径以导入现有模块
parent_dir = Path(__file__).parent.parent
sys.path.insert(0, str(parent_dir))

# 加载父目录的.env文件
load_dotenv(parent_dir / '.env')

from audio_manager import AudioDeviceManager, AudioConfig
from realtime_dialog_client import RealtimeDialogClient
import config as app_config

# 配置日志
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = FastAPI(title="豆包语音对话系统", description="基于FastAPI的实时语音对话应用")

# 静态文件目录
app.mount("/static", StaticFiles(directory="static"), name="static")

class AudioData(BaseModel):
    audio: str  # base64编码的音频数据
    type: str = "audio/pcm"

class ConnectionManager:
    def __init__(self):
        self.active_connections: list[WebSocket] = []
        self.session_manager: Dict[str, 'WebSession'] = {}

    async def connect(self, websocket: WebSocket):
        await websocket.accept()
        self.active_connections.append(websocket)
        session_id = str(id(websocket))
        self.session_manager[session_id] = WebSession(session_id, websocket)
        logger.info(f"客户端连接: {session_id}")
        return session_id

    def disconnect(self, session_id: str):
        if session_id in self.session_manager:
            self.session_manager[session_id].cleanup()
            del self.session_manager[session_id]
        logger.info(f"客户端断开连接: {session_id}")

    async def send_personal_message(self, session_id: str, message: Dict):
        if session_id in self.session_manager:
            websocket = self.session_manager[session_id].websocket
            try:
                await websocket.send_json(message)
            except Exception as e:
                logger.error(f"发送消息失败: {e}")

manager = ConnectionManager()

class WebSession:
    def __init__(self, session_id: str, websocket: WebSocket):
        self.session_id = session_id
        self.websocket = websocket
        self.client = None
        self.audio_device = None
        self.is_connected = False
        self.listener_task = None

    async def log_to_client(self, message: str, level: str = "info"):
        """向客户端发送日志"""
        try:
            await self.websocket.send_json({
                "type": "log",
                "level": level,
                "message": message
            })
        except Exception as e:
            logger.error(f"Failed to send log to client: {e}")

    async def initialize(self):
        """初始化会话"""
        await self.log_to_client("开始初始化会话...")
        try:
            # 创建音频设备管理器
            self.audio_device = AudioDeviceManager(
                AudioConfig(**app_config.input_audio_config),
                AudioConfig(**app_config.output_audio_config)
            )
            
            # 创建对话客户端
            self.client = RealtimeDialogClient(
                config=app_config.ws_connect_config,
                session_id=str(id(self.websocket))
            )
            
            # 建立连接
            await self.client.connect()
            self.is_connected = True
            
            # 创建并启动后台监听任务
            self.listener_task = asyncio.create_task(self.listen_for_responses())
            
            logger.info(f"会话初始化成功: {self.session_id}")
            await self.log_to_client(f"会话初始化成功: {self.session_id}")
            
        except Exception as e:
            logger.error(f"会话初始化失败: {e}")
            await self.log_to_client(f"会话初始化失败: {e}", "error")
            raise

    async def listen_for_responses(self):
        """后台持续监听来自豆包API的响应"""
        try:
            while self.is_connected:
                response = await self.client.receive_server_response()
                await self.log_to_client(f"收到服务端响应: {response.get('message_type')}")
                # 将响应直接发给客户端
                await self.websocket.send_json(response)
        except WebSocketDisconnect:
            logger.info("客户端在监听时断开连接。")
        except Exception as e:
            if self.is_connected:
                logger.error(f"监听响应时出错: {e}")
                await self.log_to_client(f"监听响应时出错: {e}", "error")

    async def stop_listening(self):
        """停止后台监听任务"""
        if self.listener_task and not self.listener_task.done():
            self.listener_task.cancel()
            try:
                await self.listener_task
            except asyncio.CancelledError:
                logger.info("监听任务已取消。")

    async def process_audio(self, audio_data: bytes):
        """处理音频数据，现在只负责发送"""
        if not self.is_connected or not self.client:
            await self.log_to_client("会话未连接，无法处理音频", "error")
            raise Exception("会话未连接")
        
        await self.log_to_client("发送音频数据到豆包API...")
        
        try:
            # 只发送音频，不再等待响应
            await self.client.task_request(audio_data)
            await self.log_to_client("音频数据已发送。")
        except Exception as e:
            logger.error(f"发送音频失败: {e}")
            await self.log_to_client(f"发送音频失败: {e}", "error")
            raise

    def cleanup(self):
        """清理资源"""
        asyncio.create_task(self.stop_listening())
        if self.client:
            asyncio.create_task(self.client.close())
        if self.audio_device:
            self.audio_device.cleanup()
        self.is_connected = False

@app.get("/", response_class=HTMLResponse)
async def read_root():
    """返回主页面"""
    html_content = """
<!DOCTYPE html>
<html lang="zh-CN">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>豆包语音对话系统</title>
    <link rel="stylesheet" href="/static/style.css">
</head>
<body>
    <div class="container">
        <h1>豆包语音对话系统</h1>
        <div class="dialog-container">
            <div id="dialog-box" class="dialog-box">
                <div class="message system">
                    <span class="sender">系统：</span>
                    <span class="content">欢迎使用豆包语音对话系统！按住下方按钮开始对话。</span>
                </div>
            </div>
            <div class="controls">
                <button id="voice-btn" class="voice-btn" ontouchstart="startRecording()" ontouchend="stopRecording()" onmousedown="startRecording()" onmouseup="stopRecording()">
                    <span class="btn-text">按住对话</span>
                    <span class="recording-indicator" style="display: none;">🎤 录音中...</span>
                </button>
                <button id="clear-btn" class="clear-btn" onclick="clearDialog()">清空对话</button>
            </div>
            <div id="status" class="status">准备就绪</div>
            <div id="connection-log" class="connection-log">
                <div class="log-header">
                    <h3>连接日志</h3>
                    <button onclick="clearLog()" class="clear-log-btn">清空日志</button>
                </div>
                <div id="log-content" class="log-content"></div>
            </div>
        </div>
    </div>

    <script src="/static/app.js"></script>
</body>
</html>
    """
    return html_content

@app.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket):
    """WebSocket端点"""
    session_id = await manager.connect(websocket)
    session = manager.session_manager[session_id]

    await session.log_to_client(f"客户端 {session_id} 已连接")
    
    try:
        # 初始化会话
        await session.initialize()
        
        # 发送欢迎消息
        await manager.send_personal_message(session_id, {
            "type": "welcome",
            "message": "系统已连接，可以开始对话了"
        })
        
        while True:
            # 接收消息
            data = await websocket.receive_json()
            
            if data["type"] == "audio":
                # 处理音频数据
                audio_bytes = base64.b64decode(data["audio"])
                
                try:
                    # 添加用户消息
                    await manager.send_personal_message(session_id, {
                        "type": "user_message",
                        "message": "我：",
                        "text": "（语音输入已发送）"
                    })
                    
                    # 发送到豆包API并由process_audio处理响应
                    await session.process_audio(audio_bytes)
                    
                except Exception as e:
                    await manager.send_personal_message(session_id, {
                        "type": "error",
                        "message": "错误",
                        "text": str(e)
                    })
            
            elif data["type"] == "clear":
                await manager.send_personal_message(session_id, {
                    "type": "clear"
                })
                
    except WebSocketDisconnect:
        manager.disconnect(session_id)
    except Exception as e:
        logger.error(f"WebSocket错误: {e}")
        manager.disconnect(session_id)

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8002)
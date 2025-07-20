import os
import sys
import asyncio
import json
import base64
import logging
from pathlib import Path
from typing import Dict, Any

from fastapi import FastAPI, WebSocket, WebSocketDisconnect, HTTPException, Request
from fastapi.staticfiles import StaticFiles
from fastapi.responses import HTMLResponse,  JSONResponse
from pydantic import BaseModel
from dotenv import load_dotenv

# 添加父目录到路径以导入现有模块
parent_dir = Path(__file__).parent.parent
sys.path.insert(0, str(parent_dir))

# 加载父目录的.env文件
load_dotenv(parent_dir / '.env')

import config as app_config
from audio_manager import DialogSession, AudioDeviceManager, AudioConfig
from realtime_dialog_client import RealtimeDialogClient

# 配置日志
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = FastAPI(title="豆包语音对话系统", description="基于FastAPI的实时语音对话应用")

# 静态文件目录
static_dir = Path(__file__).parent / "static"
if static_dir.exists():
    app.mount("/static", StaticFiles(directory=str(static_dir)), name="static")
else:
    logger.warning(f"Static directory not found: {static_dir}")

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
        self.is_connected = False
        self.is_dialog_active = False
        self.response_task = None
        
        # 缓存最后一次的事件结果
        self.last_user_text = ""           # 最后一次event 451的结果
        self.last_ai_response = ""         # 最后一次event 550的结果
        self.user_message_sent = False     # 是否已发送用户消息气泡
        self.ai_response_sent = False      # 是否已发送AI回复气泡
        
        # 调试计数器
        self.event_500_count = 0
        self.event_550_count = 0
        self.force_reply_timer = None
        
        # 550事件内容收集器
        self.ai_response_parts = []        # 收集所有550事件的内容
        self.ai_final_response = ""        # 组合后的完整回复
        self.ai_response_timer = None      # 定时器，用于检测550事件结束
        
    def reset_conversation_state(self):
        """重置对话状态，准备新一轮对话"""
        self.last_user_text = ""
        self.last_ai_response = ""
        self.user_message_sent = False
        self.ai_response_sent = False
        self.event_500_count = 0
        self.event_550_count = 0
        
        # 重置550事件收集器
        self.ai_response_parts = []
        self.ai_final_response = ""
        
        # 取消定时器
        if self.ai_response_timer:
            self.ai_response_timer.cancel()
            self.ai_response_timer = None
        
        # 取消之前的强制回复定时器
        if self.force_reply_timer:
            self.force_reply_timer.cancel()
            self.force_reply_timer = None

    async def initialize(self):
        """初始化会话 - 类似main.py的DialogSession"""
        try:
            # 创建对话客户端
            self.client = RealtimeDialogClient(
                config=app_config.ws_connect_config,
                session_id=self.session_id
            )
            
            # 建立连接
            await self.client.connect()
            await self.client.say_hello()
            self.is_connected = True
            logger.info(f"会话初始化成功: {self.session_id}")
            
        except Exception as e:
            logger.error(f"会话初始化失败: {e}")
            raise

    async def start_dialog_mode(self):
        """开启对话模式 - 启动持续响应处理"""
        if self.is_dialog_active:
            return
            
        self.is_dialog_active = True
        # 启动响应处理任务
        self.response_task = asyncio.create_task(self.continuous_response_handler())
        logger.info(f"对话模式已开启: {self.session_id}")

    async def stop_dialog_mode(self):
        """停止对话模式"""
        self.is_dialog_active = False
        
        if self.response_task:
            self.response_task.cancel()
            try:
                await self.response_task
            except asyncio.CancelledError:
                pass
            self.response_task = None
        
        logger.info(f"对话模式已停止: {self.session_id}")

    async def continuous_response_handler(self):
        """持续处理服务器响应 - 类似main.py的receive_loop"""
        try:
            while self.is_dialog_active:
                response = await self.client.receive_server_response()
                await self.handle_server_response(response)
                
                # 检查会话结束事件
                if response.get('event') in [152, 153]:
                    logger.info(f"会话结束: event={response.get('event')}")
                    break
                    
        except asyncio.CancelledError:
            logger.info("响应处理任务已取消")
        except Exception as e:
            logger.error(f"响应处理错误: {e}")
            await manager.send_personal_message(self.session_id, {
                "type": "error",
                "message": "错误",
                "text": f"响应处理异常: {e}"
            })

    async def handle_server_response(self, response: Dict[str, Any]):
        """处理服务器响应 - 只显示最后一次的451和550，强化调试"""
        if response == {}:
            return
            
        # 详细日志记录
        event = response.get('event')
        message_type = response.get('message_type')
        payload_msg = response.get('payload_msg', {})
        
        logger.info(f"🔄 处理响应: message_type={message_type}, event={event}, payload_type={type(payload_msg)}")
        
        # 发送调试信息到前端
        await manager.send_personal_message(self.session_id, {
            "type": "debug_info",
            "message": f"🔄 收到事件{event} (类型:{message_type})",
            "event": event,
            "message_type": message_type
        })
        
        # 音频响应 - 类似本地版本的音频处理
        if response.get('message_type') == 'SERVER_ACK' and isinstance(response.get('payload_msg'), bytes):
            audio_data = response['payload_msg']
            logger.info(f"🔊 接收到音频数据: {len(audio_data)} 字节")
            
            # 发送音频数据到前端播放，使用base64编码
            # 根据config.py中的output_audio_config配置
            await manager.send_personal_message(self.session_id, {
                "type": "audio_stream",
                "audio": base64.b64encode(audio_data).decode('utf-8'),
                "format": "pcm",
                "sample_rate": 24000,  # 来自output_audio_config
                "channels": 1,
                "bit_depth": 32,  # pyaudio.paFloat32
                "audio_format": "float32"
            })
            
        # 文本响应
        elif response.get('message_type') == 'SERVER_FULL_RESPONSE':
            
            # Event 450: 检测到用户开始说话 - 重置对话状态
            if event == 450:
                logger.info("🎤 检测到用户开始说话，重置对话状态")
                self.reset_conversation_state()
                await manager.send_personal_message(self.session_id, {
                    "type": "status_update",
                    "message": "正在识别语音..."
                })
                
            # Event 451: ASR识别结果 - 缓存最新结果
            elif event == 451 and isinstance(payload_msg, dict) and "results" in payload_msg:
                results_list = payload_msg["results"]
                if results_list and isinstance(results_list, list) and "text" in results_list[0]:
                    # 更新缓存的用户文本，但不立即发送气泡
                    self.last_user_text = results_list[0]["text"]
                    logger.info(f"💬 缓存用户语音: {self.last_user_text}")
                    
            # Event 459: 用户说话结束 - 发送最终的用户消息气泡
            elif event == 459:
                logger.info("✋ 用户说话结束，发送最终用户消息")
                if self.last_user_text and not self.user_message_sent:
                    await manager.send_personal_message(self.session_id, {
                        "type": "user_message",
                        "message": "我：",
                        "text": self.last_user_text
                    })
                    self.user_message_sent = True
                    logger.info(f"✅ 已发送用户消息: {self.last_user_text}")
                    
                await manager.send_personal_message(self.session_id, {
                    "type": "status_update",
                    "message": "语音识别完成，AI思考中..."
                })
                
            # Event 500: AI中间回复 - 仅记录，绝不显示
            elif event == 500 and "content" in payload_msg:
                self.event_500_count += 1
                # 仅更新缓存，绝对不发送任何消息气泡
                self.last_ai_response = payload_msg["content"]
                logger.info(f"🤖 AI中间回复(500-{self.event_500_count}): {payload_msg['content']} [仅缓存，绝不显示]")
                # 只更新状态，不显示消息内容
                await manager.send_personal_message(self.session_id, {
                    "type": "status_update",
                    "message": "AI正在思考中..."
                })
                
            # Event 550: AI最终回复 - 收集所有550内容，组合成完整回复
            elif event == 550 and "content" in payload_msg:
                self.event_550_count += 1
                content = payload_msg["content"]
                
                # 收集550事件的内容
                self.ai_response_parts.append(content)
                self.last_ai_response = content  # 保存最后一个550的内容
                
                logger.info(f"🎯 收到AI回复片段(550-{self.event_550_count}): {content}")
                
                # 组合所有550事件的内容成为完整回复
                self.ai_final_response = "".join(self.ai_response_parts)
                
                # 如果还没有发送AI回复，立即发送当前组合的完整内容
                if not self.ai_response_sent:
                    await manager.send_personal_message(self.session_id, {
                        "type": "assistant_message",
                        "message": "豆包：",
                        "text": self.ai_final_response
                    })
                    self.ai_response_sent = True
                    logger.info(f"✅ 首次发送AI完整回复: {self.ai_final_response}")
                else:
                    # 如果已经发送过，更新现有的消息内容
                    await manager.send_personal_message(self.session_id, {
                        "type": "assistant_message_update",
                        "message": "豆包：",
                        "text": self.ai_final_response
                    })
                    logger.info(f"🔄 更新AI完整回复: {self.ai_final_response}")
                
                # 重置定时器，2秒后标记AI回复完成
                if self.ai_response_timer:
                    self.ai_response_timer.cancel()
                
                self.ai_response_timer = asyncio.create_task(self._ai_response_completion_timer())
                
                logger.info(f"📊 本轮550统计: {self.event_550_count}个片段, 完整回复长度: {len(self.ai_final_response)}字符")
                
                # 发送状态更新
                await manager.send_personal_message(self.session_id, {
                    "type": "status_update",
                    "message": f"AI回复更新中... ({self.event_550_count}个片段)"
                })
                
            # 其他事件 - 仅记录日志，绝不显示任何消息气泡
            else:
                logger.info(f"❓ 收到其他事件: event={event}, payload={payload_msg}")
                
                # 仅记录到日志，绝对不发送任何消息气泡，确保界面干净
                if isinstance(payload_msg, dict) and "content" in payload_msg:
                    content = payload_msg["content"]
                    logger.info(f"📝 仅记录未处理的content事件{event}: {content} [不显示]")
                    
                    # 只发送调试信息到日志，不影响用户界面
                    await manager.send_personal_message(self.session_id, {
                        "type": "debug_info",
                        "message": f"📝 记录事件{event}但未显示内容"
                    })
                
                # 字符串类型的payload也只记录，不显示
                elif isinstance(payload_msg, str) and payload_msg.strip():
                    logger.info(f"📝 仅记录字符串响应事件{event}: {payload_msg} [不显示]")
                    await manager.send_personal_message(self.session_id, {
                        "type": "debug_info", 
                        "message": f"📝 记录字符串事件{event}但未显示"
                    })
                
        # 错误响应
        elif response.get('message_type') == 'SERVER_ERROR_RESPONSE':
            error_detail = str(response.get('payload_msg', '未知错误'))
            logger.error(f"❌ 服务器错误: {error_detail}")
            await manager.send_personal_message(self.session_id, {
                "type": "error",
                "message": "错误",
                "text": f"服务器错误: {error_detail}"
            })
        
        # 兜底：记录所有未处理的响应
        else:
            logger.warning(f"🔍 未处理的响应类型: {response}")
            await manager.send_personal_message(self.session_id, {
                "type": "debug_info",
                "message": f"🔍 未处理响应: {response}"
            })

    async def send_audio_chunk(self, audio_data: bytes):
        """发送音频块 - 流式发送"""
        if not self.is_connected or not self.client or not self.is_dialog_active:
            return
            
        try:
            await self.client.task_request(audio_data)
        except Exception as e:
            logger.error(f"发送音频失败: {e}")

    def cleanup(self):
        """清理资源"""
        asyncio.create_task(self.stop_dialog_mode())
        if self.client:
            asyncio.create_task(self.client.close())
        self.is_connected = False

    async def _ai_response_completion_timer(self):
        """AI回复完成定时器 - 2秒后标记AI回复完成"""
        try:
            await asyncio.sleep(2.0)  # 等待2秒
            
            if self.ai_response_sent and self.ai_final_response:
                logger.info(f"⏰ AI回复完成定时器触发，最终回复: {self.ai_final_response}")
                await manager.send_personal_message(self.session_id, {
                    "type": "status_update",
                    "message": f"AI回复完成 (共{self.event_550_count}个片段，{len(self.ai_final_response)}字符)"
                })
                
        except asyncio.CancelledError:
            logger.info("AI回复完成定时器被取消")
        except Exception as e:
            logger.error(f"AI回复完成定时器错误: {e}")

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
                <button id="voice-btn" class="voice-btn" onclick="toggleDialog()">
                    <span class="btn-text">开启对话</span>
                    <span class="recording-indicator" style="display: none;">🎤 对话中...</span>
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
    """WebSocket端点 - 流式对话模式，类似main.py流程"""
    session_id = await manager.connect(websocket)
    try:
        session = manager.session_manager[session_id]
        
        # 初始化会话
        try:
            await session.initialize()
            logger.info(f"会话初始化成功: {session_id}")
            await manager.send_personal_message(session_id, {
                "type": "welcome",
                "message": "系统已连接，可以开启对话了"
            })
        except Exception as init_error:
            logger.error(f"会话初始化失败: {init_error}")
            await manager.send_personal_message(session_id, {
                "type": "welcome",
                "message": "系统已连接（降级模式），豆包API暂时不可用"
            })
        
        # 主消息循环
        while True:
            data = await websocket.receive_json()
            
            if data["type"] == "start_dialog":
                # 开启对话模式
                try:
                    if session.is_connected and session.client:
                        await session.start_dialog_mode()
                        await manager.send_personal_message(session_id, {
                            "type": "status_update",
                            "message": "对话模式已开启，可以开始说话"
                        })
                    else:
                        raise Exception("豆包API未连接")
                except Exception as e:
                    logger.error(f"开启对话模式失败: {e}")
                    await manager.send_personal_message(session_id, {
                        "type": "error",
                        "message": "错误",
                        "text": f"开启对话失败: {e}"
                    })
                    
            elif data["type"] == "stop_dialog":
                # 停止对话模式
                await session.stop_dialog_mode()
                await manager.send_personal_message(session_id, {
                    "type": "status_update",
                    "message": "对话模式已停止"
                })
                
            elif data["type"] == "audio_stream":
                # 流式音频数据
                if session.is_dialog_active and session.is_connected and session.client:
                    try:
                        audio_bytes = base64.b64decode(data["audio"])
                        await session.send_audio_chunk(audio_bytes)
                    except Exception as e:
                        logger.error(f"处理音频流失败: {e}")
                        
            elif data["type"] == "clear":
                await manager.send_personal_message(session_id, {"type": "clear"})
                
    except WebSocketDisconnect:
        manager.disconnect(session_id)
    except Exception as e:
        logger.error(f"WebSocket错误: {e}")
        manager.disconnect(session_id)

@app.get("/.well-known/appspecific/com.chrome.devtools.json")
async def chrome_devtools():
    """处理Chrome DevTools请求，避免404错误"""
    return {"status": "ok", "message": "Chrome DevTools endpoint"}

@app.get("/json/version")
async def devtools_version():
    """DevTools版本信息"""
    return {
        "Browser": "豆包语音对话系统",
        "Protocol-Version": "1.0",
        "User-Agent": "DouBao-Voice-Chat/1.0"
    }

@app.get("/json")
async def devtools_info():
    """DevTools信息"""
    return []

@app.exception_handler(404)
async def not_found_handler(request: Request, exc: HTTPException):
    """自定义404处理器"""
    # 如果是开发者工具相关请求，返回简单的OK响应
    if ".well-known" in str(request.url) or "devtools" in str(request.url):
        return JSONResponse(status_code=200, content={"status": "ok"})
    
    # 其他404请求返回标准错误
    return JSONResponse(
        status_code=404,
        content={"detail": f"路径 {request.url.path} 未找到"}
    )

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)

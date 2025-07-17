import uuid
import pyaudio
from dotenv import load_dotenv
import os

# 加载环境变量
load_dotenv()

# 从环境变量获取API凭证
X_API_APP_ID = os.getenv("X-Api-App-ID")
X_API_ACCESS_KEY = os.getenv("X-Api-Access-Key")

# 验证必要的环境变量
if not X_API_APP_ID or not X_API_ACCESS_KEY:
    raise ValueError(
        "Missing required environment variables. "
        "Please set X-Api-App-ID and X-Api-Access-Key in your .env file."
    )

# 配置信息
ws_connect_config = {
    "base_url": "wss://openspeech.bytedance.com/api/v3/realtime/dialogue",
    "headers": {
        "X-Api-App-ID": X_API_APP_ID,
        "X-Api-Access-Key": X_API_ACCESS_KEY,
        "X-Api-Resource-Id": "volc.speech.dialog",  # 固定值
        "X-Api-App-Key": "PlgvMymc7f3tQnJ6",  # 固定值
        "X-Api-Connect-Id": str(uuid.uuid4()),
    }
}

start_session_req = {
    "tts": {
        "audio_config": {
            "channel": 1,
            "format": "pcm",
            "sample_rate": 24000
        },
    },
    "dialog": {
        "bot_name": "豆包",
        "system_role": "你使用活泼灵动的女声，性格开朗，热爱生活。",
        "speaking_style": "你的说话风格简洁明了，语速适中，语调自然。",
        "extra": {
            "strict_audit": False,
            "audit_response": "支持客户自定义安全审核回复话术。"
        }
    }
}

input_audio_config = {
    "chunk": 3200,
    "format": "pcm",
    "channels": 1,
    "sample_rate": 16000,
    "bit_size": pyaudio.paInt16
}

output_audio_config = {
    "chunk": 3200,
    "format": "pcm",
    "channels": 1,
    "sample_rate": 24000,
    "bit_size": pyaudio.paFloat32
}

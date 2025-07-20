// 初始化变量
let ws = null;
let isRecording = false;
let mediaRecorder = null;
let audioStream = null;
let audioContext = null;
let audioBufferQueue = [];
let isPlaying = false;


// 音频配置
const AUDIO_CONFIG = {
    sampleRate: 16000,
    channelCount: 1,
    echoCancellation: true,
    noiseSuppression: true
};

// 添加日志到界面
function addLog(message, level = 'info') {
    const logContent = document.getElementById('log-content');
    if (!logContent) return;
    
    const timestamp = new Date().toLocaleTimeString('zh-CN');
    const logEntry = document.createElement('div');
    logEntry.className = `log-entry ${level}`;
    
    logEntry.innerHTML = `
        <span class="log-timestamp">[${timestamp}]</span>
        <span class="log-message">${message}</span>
    `;
    
    logContent.appendChild(logEntry);
    logContent.scrollTop = logContent.scrollHeight;
    
    // 限制日志条目数量
    const maxLogs = 100;
    while (logContent.children.length > maxLogs) {
        logContent.removeChild(logContent.firstChild);
    }
}

// 清空日志
function clearLog() {
    const logContent = document.getElementById('log-content');
    if (logContent) {
        logContent.innerHTML = '';
    }
}

// 初始化WebSocket
function initializeWebSocket() {
    const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
    const wsUrl = `${protocol}//${window.location.host}/ws`;
    
    ws = new WebSocket(wsUrl);
    
    ws.onopen = function(event) {
        addLog('WebSocket连接成功');
        updateStatus('已连接，请按住按钮开始对话');
    };
    
    ws.onmessage = function(event) {
        const data = JSON.parse(event.data);
        handleServerMessage(data);
    };
    
    ws.onclose = function(event) {
        addLog('WebSocket连接断开', 'error');
        updateStatus('连接已断开，正在尝试重新连接...');
        
        // 3秒后尝试重连
        setTimeout(() => {
            if (!ws || ws.readyState === WebSocket.CLOSED) {
                initializeWebSocket();
            }
        }, 3000);
    };
    
    ws.onerror = function(error) {
        addLog('WebSocket发生错误', 'error');
        updateStatus('连接错误');
    };
}

// 处理服务器消息
function handleServerMessage(data) {
    addLog(`收到消息: ${data.type || data.message_type}`, 'debug');

    switch(data.type) {
        case 'welcome':
            addMessage('系统', data.message, 'system');
            break;
        case 'log':
            addLog(`[服务端] ${data.message}`, data.level);
            break;
        case 'user_message':
            // 客户端自行添加，此处忽略
            break;
        case 'assistant_message':
            // 更新或添加小助手的消息
            updateAssistantMessage(data.text);
            break;
        case 'error':
            addMessage('错误', data.text, 'error');
            break;
        case 'clear':
            clearDialog();
            break;
    }

    // 处理来自豆包API的原始消息
    switch(data.message_type) {
        case 'SERVER_ACK':
            // 如果payload是字节(音频数据)，则解码并播放
            if (data.payload_msg && typeof data.payload_msg === 'string') {
                const audioData = base64ToBuffer(data.payload_msg);
                playAudio(audioData);
            }
            break;
        case 'SERVER_FULL_RESPONSE':
            if (data.payload_msg && data.payload_msg.content) {
                updateAssistantMessage(data.payload_msg.content);
            }
            break;
        case 'SERVER_ERROR_RESPONSE':
            addMessage('豆包API错误', data.payload_msg, 'error');
            break;
    }
}

// 添加消息到对话框
function addMessage(sender, text, type) {
    const dialogBox = document.getElementById('dialog-box');
    const messageDiv = document.createElement('div');
    messageDiv.className = `message ${type}`;
    
    messageDiv.innerHTML = `
        <span class="sender">${sender}：</span>
        <span class="content">${text}</span>
    `;
    
    dialogBox.appendChild(messageDiv);
    dialogBox.scrollTop = dialogBox.scrollHeight; // 滚动到底部
}

// 更新或添加小助手的消息
function updateAssistantMessage(text) {
    const dialogBox = document.getElementById('dialog-box');
    let lastMessage = dialogBox.lastElementChild;

    // 如果最后一条消息是小助手的，则更新它；否则，创建新的
    if (lastMessage && lastMessage.classList.contains('assistant')) {
        lastMessage.querySelector('.content').textContent = text;
    } else {
        addMessage('豆包', text, 'assistant');
    }
}


// 更新状态
function updateStatus(text) {
    document.getElementById('status').textContent = text;
}

// 开始录音
async function startRecording() {
    if (!ws || ws.readyState !== WebSocket.OPEN) {
        alert('WebSocket尚未连接，请稍后再试');
        return;
    }
    
    if (isRecording) return;

    try {
        addLog('开始录音...');
        audioStream = await navigator.mediaDevices.getUserMedia({ audio: AUDIO_CONFIG });
        
        mediaRecorder = new MediaRecorder(audioStream);
        const audioChunks = [];
        
        mediaRecorder.ondataavailable = (event) => {
            if (event.data.size > 0) {
                audioChunks.push(event.data);
            }
        };
        
        mediaRecorder.onstop = async () => {
            const audioBlob = new Blob(audioChunks, { type: 'audio/webm' });
            const pcmData = await convertBlobToPCM(audioBlob);
            
            if (ws && ws.readyState === WebSocket.OPEN) {
                const base64Audio = arrayBufferToBase64(pcmData);
                ws.send(JSON.stringify({
                    type: 'audio',
                    audio: base64Audio
                }));
                addLog('音频数据已发送');
            }
            
            audioChunks.length = 0;
        };
        
        mediaRecorder.start();
        isRecording = true;
        
        document.getElementById('voice-btn').classList.add('recording');
        document.querySelector('.btn-text').style.display = 'none';
        document.querySelector('.recording-indicator').style.display = 'inline';
        updateStatus('录音中...');
        
        addMessage('我', '（正在说话...）', 'user');
        
    } catch (error) {
        addLog(`录音失败: ${error}`, 'error');
        alert('无法启动录音，请检查麦克风权限');
    }
}

// 停止录音
function stopRecording() {
    if (!isRecording || !mediaRecorder) return;
    
    addLog('停止录音');
    mediaRecorder.stop();
    
    if (audioStream) {
        audioStream.getTracks().forEach(track => track.stop());
    }
    
    isRecording = false;
    
    document.getElementById('voice-btn').classList.remove('recording');
    document.querySelector('.btn-text').style.display = 'inline';
    document.querySelector('.recording-indicator').style.display = 'none';
    updateStatus('处理中...');
}

// 将Blob转换为PCM
async function convertBlobToPCM(blob) {
    const arrayBuffer = await blob.arrayBuffer();
    const tempAudioContext = new (window.AudioContext || window.webkitAudioContext)({ sampleRate: AUDIO_CONFIG.sampleRate });
    const audioBuffer = await tempAudioContext.decodeAudioData(arrayBuffer);
    
    // 如果采样率不匹配，进行重采样
    if (audioBuffer.sampleRate !== AUDIO_CONFIG.sampleRate) {
        const offlineContext = new OfflineAudioContext(
            audioBuffer.numberOfChannels,
            audioBuffer.duration * AUDIO_CONFIG.sampleRate,
            AUDIO_CONFIG.sampleRate
        );
        const source = offlineContext.createBufferSource();
        source.buffer = audioBuffer;
        source.connect(offlineContext.destination);
        source.start();
        const resampledBuffer = await offlineContext.startRendering();
        return convertAudioBufferToPCM(resampledBuffer);
    }
    
    return convertAudioBufferToPCM(audioBuffer);
}

function convertAudioBufferToPCM(audioBuffer) {
    const pcmData = new Int16Array(audioBuffer.length);
    const channelData = audioBuffer.getChannelData(0); // 单声道
    for (let i = 0; i < audioBuffer.length; i++) {
        pcmData[i] = Math.max(-1, Math.min(1, channelData[i])) * 0x7FFF;
    }
    return pcmData.buffer;
}

// ArrayBuffer到Base64
function arrayBufferToBase64(buffer) {
    const bytes = new Uint8Array(buffer);
    let binary = '';
    for (let i = 0; i < bytes.byteLength; i++) {
        binary += String.fromCharCode(bytes[i]);
    }
    return btoa(binary);
}

// Base64到ArrayBuffer
function base64ToBuffer(base64) {
    const binary_string = window.atob(base64);
    const len = binary_string.length;
    const bytes = new Uint8Array(len);
    for (let i = 0; i < len; i++) {
        bytes[i] = binary_string.charCodeAt(i);
    }
    return bytes.buffer;
}


// 播放音频
async function playAudio(arrayBuffer) {
    if (!audioContext) {
        audioContext = new (window.AudioContext || window.webkitAudioContext)();
    }
    
    try {
        const audioBuffer = await audioContext.decodeAudioData(arrayBuffer.slice(0));
        audioBufferQueue.push(audioBuffer);
        if (!isPlaying) {
            playQueue();
        }
    } catch (e) {
        addLog(`音频解码失败: ${e}`, 'error');
    }
}

function playQueue() {
    if (audioBufferQueue.length === 0) {
        isPlaying = false;
        return;
    }

    isPlaying = true;
    const buffer = audioBufferQueue.shift();
    const source = audioContext.createBufferSource();
    source.buffer = buffer;
    source.connect(audioContext.destination);
    source.onended = playQueue;
    source.start();
}


// 清空对话
function clearDialog() {
    const dialogBox = document.getElementById('dialog-box');
    dialogBox.innerHTML = `
        <div class="message system">
            <span class="sender">系统：</span>
            <span class="content">对话已清空。按住下方按钮开始新的对话。</span>
        </div>
    `;
    if(ws && ws.readyState === WebSocket.OPEN) {
        ws.send(JSON.stringify({ type: 'clear' }));
    }
}

// 页面加载完成时初始化
window.addEventListener('load', function() {
    initializeWebSocket();
    
    if (!navigator.mediaDevices || !navigator.mediaDevices.getUserMedia) {
        alert('您的浏览器不支持录音功能');
    }
});

// 添加键盘快捷键
document.addEventListener('keydown', (e) => {
    if (e.code === 'Space' && !e.repeat) {
        e.preventDefault();
        startRecording();
    }
});

document.addEventListener('keyup', (e) => {
    if (e.code === 'Space') {
        e.preventDefault();
        stopRecording();
    }
});

// 页面关闭前清理
window.addEventListener('beforeunload', () => {
    if (ws) {
        ws.close();
    }
});

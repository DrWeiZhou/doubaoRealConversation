// 初始化变量
let ws = null;
let isDialogActive = false;
let mediaRecorder = null;
let audioStream = null;
let connectionLog = [];
let audioContext = null;
let processor = null;

// 音频播放队列管理 (类似本地版本的audio_queue)
let audioQueue = [];
let isAudioPlaying = false;
let audioPlaybackContext = null;

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
    const maxLogs = 50;
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

// 初始化WebSocket连接
function initializeWebSocket() {
    const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
    const wsUrl = `${protocol}//${window.location.host}/ws`;
    
    addLog(`尝试连接到: ${wsUrl}`);
    
    ws = new WebSocket(wsUrl);
    
    ws.onopen = function(event) {
        addLog('WebSocket连接已建立', 'success');
        updateStatus('已连接');
    };
    
    ws.onmessage = function(event) {
        try {
            const data = JSON.parse(event.data);
            handleServerMessage(data);
        } catch (error) {
            addLog('解析消息错误: ' + error.message, 'error');
        }
    };
    
    ws.onclose = function(event) {
        addLog(`WebSocket连接关闭: ${event.code} - ${event.reason}`, 'warning');
        updateStatus('连接已断开');
        
        if (isDialogActive) {
            stopDialog();
        }
        
        // 自动重连
        setTimeout(() => {
            addLog('尝试重新连接...', 'info');
            initializeWebSocket();
        }, 3000);
    };
    
    ws.onerror = function(error) {
        addLog('WebSocket错误: ' + error, 'error');
        updateStatus('连接错误');
    };
}

// 处理服务器消息
function handleServerMessage(data) {
    addLog(`收到消息: ${data.type} - ${JSON.stringify(data)}`, 'info');
    
    switch (data.type) {
        case 'welcome':
            addMessage('系统', data.message, 'system');
            break;
            
        case 'user_message':
            addLog(`✅ 显示用户消息: ${data.text}`, 'success');
            addMessage(data.message, data.text, 'user');
            break;
            
        case 'assistant_message':
            addLog(`✅ 显示豆包消息: ${data.text}`, 'success');
            addMessage(data.message, data.text, 'assistant');
            break;
            
        case 'assistant_message_update':
            addLog(`🔄 更新豆包消息: ${data.text}`, 'success');
            updateLastAssistantMessage(data.message, data.text);
            break;
            
        case 'audio_stream':
            // 传递音频配置信息到播放函数
            const audioConfig = {
                sample_rate: data.sample_rate,
                channels: data.channels,
                format: data.format,
                audio_format: data.audio_format,
                bit_depth: data.bit_depth
            };
            playAudioStream(data.audio, audioConfig);
            break;
            
        case 'processing':
            updateStatus('处理中...');
            break;
            
        case 'error':
            addMessage(data.message, data.text, 'error');
            updateStatus('错误');
            break;
            
        case 'clear':
            clearDialog();
            break;
            
        case 'status_update':
            updateStatus(data.message);
            break;
            
        case 'debug_info':
            addLog(`🔍 调试信息: ${data.message}`, 'debug');
            
            // 检查是否是事件450 (用户开始说话) - 类似本地版本清空音频队列
            if (data.message && data.message.includes('事件450')) {
                addLog('🗑️ 检测到用户开始说话，清空音频队列', 'info');
                clearAudioQueue();
            }
            break;
            
        default:
            addLog(`⚠️ 未知消息类型: ${data.type}`, 'warning');
            // 如果消息包含text字段，尝试显示
            if (data.text) {
                addMessage('未知', data.text, 'system');
            }
            break;
    }
}

// 开启/关闭对话
async function toggleDialog() {
    if (!isDialogActive) {
        await startDialog();
    } else {
        await stopDialog();
    }
}

// 开启对话
async function startDialog() {
    try {
        addLog('开启对话模式...', 'info');
        
        if (!ws || ws.readyState !== WebSocket.OPEN) {
            addLog('WebSocket未连接，无法开启对话', 'error');
            return;
        }
        
        // 发送开启对话请求
        ws.send(JSON.stringify({
            type: 'start_dialog'
        }));
        
        // 获取麦克风权限并开始录音
        audioStream = await navigator.mediaDevices.getUserMedia({
            audio: AUDIO_CONFIG
        });
        
        // 创建音频上下文
        audioContext = new (window.AudioContext || window.webkitAudioContext)({
            sampleRate: AUDIO_CONFIG.sampleRate
        });
        
        const source = audioContext.createMediaStreamSource(audioStream);
        
        // 创建音频处理器
        processor = audioContext.createScriptProcessor(1024, 1, 1);
        
        processor.onaudioprocess = function(e) {
            if (isDialogActive && ws && ws.readyState === WebSocket.OPEN) {
                const inputBuffer = e.inputBuffer.getChannelData(0);
                
                // 转换为16位PCM
                const pcmData = float32ToPCM16(inputBuffer);
                const base64Audio = arrayBufferToBase64(pcmData);
                
                // 发送音频数据流
                ws.send(JSON.stringify({
                    type: 'audio_stream',
                    audio: base64Audio
                }));
            }
        };
        
        source.connect(processor);
        processor.connect(audioContext.destination);
        
        isDialogActive = true;
        updateDialogButton();
        addLog('对话模式已开启', 'success');
        
    } catch (error) {
        addLog('开启对话失败: ' + error.message, 'error');
        updateStatus('麦克风权限被拒绝');
    }
}

// 关闭对话
async function stopDialog() {
    try {
        addLog('关闭对话模式...', 'info');
        
        isDialogActive = false;
        
        // 发送停止对话请求
        if (ws && ws.readyState === WebSocket.OPEN) {
            ws.send(JSON.stringify({
                type: 'stop_dialog'
            }));
        }
        
        // 停止音频流
        if (audioStream) {
            audioStream.getTracks().forEach(track => track.stop());
            audioStream = null;
        }
        
        // 清理音频上下文
        if (processor) {
            processor.disconnect();
            processor = null;
        }
        
        if (audioContext) {
            await audioContext.close();
            audioContext = null;
        }
        
        updateDialogButton();
        addLog('对话模式已关闭', 'success');
        
    } catch (error) {
        addLog('关闭对话失败: ' + error.message, 'error');
    }
}

// 更新对话按钮状态
function updateDialogButton() {
    const voiceBtn = document.getElementById('voice-btn');
    const btnText = voiceBtn.querySelector('.btn-text');
    const indicator = voiceBtn.querySelector('.recording-indicator');
    
    if (isDialogActive) {
        btnText.textContent = '关闭对话';
        indicator.style.display = 'inline';
        voiceBtn.classList.add('active');
    } else {
        btnText.textContent = '开启对话';
        indicator.style.display = 'none';
        voiceBtn.classList.remove('active');
    }
}

// 转换Float32Array到PCM16
function float32ToPCM16(float32Array) {
    const buffer = new ArrayBuffer(float32Array.length * 2);
    const view = new DataView(buffer);
    let offset = 0;
    
    for (let i = 0; i < float32Array.length; i++, offset += 2) {
        const s = Math.max(-1, Math.min(1, float32Array[i]));
        view.setInt16(offset, s < 0 ? s * 0x8000 : s * 0x7FFF, true);
    }
    
    return buffer;
}

// ArrayBuffer转Base64
function arrayBufferToBase64(buffer) {
    const bytes = new Uint8Array(buffer);
    let binary = '';
    for (let i = 0; i < bytes.byteLength; i++) {
        binary += String.fromCharCode(bytes[i]);
    }
    return window.btoa(binary);
}

// 播放音频流 - 使用队列机制 (类似本地版本)
function playAudioStream(base64Audio, audioConfig = {}) {
    try {
        // 默认配置，来自config.py的output_audio_config
        const config = {
            sampleRate: audioConfig.sample_rate || 24000,
            channels: audioConfig.channels || 1,
            format: audioConfig.audio_format || 'float32',
            ...audioConfig
        };
        
        addLog(`🎵 收到音频数据: ${base64Audio.length}字符, 配置: ${JSON.stringify(config)}`, 'info');
        
        // 将音频添加到队列中播放 (类似本地版本的audio_queue.put)
        addToAudioQueue(base64Audio, config);
        
    } catch (error) {
        addLog('音频队列添加失败: ' + error.message, 'error');
    }
}

// 播放Float32格式音频 (类似本地版本)
function playFloat32Audio(uint8Array, audioContext, config) {
    try {
        // 将字节数组转换为Float32数组
        const float32Array = new Float32Array(uint8Array.buffer);
        
        // 创建音频缓冲区
        const audioBuffer = audioContext.createBuffer(
            config.channels,
            float32Array.length / config.channels,
            config.sampleRate
        );
        
        // 填充音频数据
        for (let channel = 0; channel < config.channels; channel++) {
            const channelData = audioBuffer.getChannelData(channel);
            for (let i = 0; i < channelData.length; i++) {
                channelData[i] = float32Array[i * config.channels + channel];
            }
        }
        
        // 播放音频
        const source = audioContext.createBufferSource();
        source.buffer = audioBuffer;
        source.connect(audioContext.destination);
        source.start(0);
        
        addLog(`✅ Float32音频播放成功: ${float32Array.length}个样本`, 'success');
        
    } catch (error) {
        addLog('Float32音频播放失败: ' + error.message, 'error');
    }
}

// 播放PCM16格式音频
function playPCM16Audio(arrayBuffer, audioContext, config) {
    audioContext.decodeAudioData(arrayBuffer.slice(0), function(buffer) {
        const source = audioContext.createBufferSource();
        source.buffer = buffer;
        source.connect(audioContext.destination);
        source.start(0);
        addLog(`✅ PCM16音频播放成功`, 'success');
    }).catch(error => {
        addLog('PCM16音频播放失败: ' + error.message, 'error');
    });
}

// 音频队列管理 - 类似本地版本的音频播放线程
function initAudioQueue() {
    if (!audioPlaybackContext) {
        audioPlaybackContext = new (window.AudioContext || window.webkitAudioContext)();
    }
    
    // 启动音频播放循环
    if (!isAudioPlaying) {
        isAudioPlaying = true;
        processAudioQueue();
    }
}

function addToAudioQueue(audioData, config) {
    audioQueue.push({ audioData, config });
    addLog(`🎵 音频加入队列，队列长度: ${audioQueue.length}`, 'info');
    
    // 确保队列处理正在运行
    if (!isAudioPlaying) {
        initAudioQueue();
    }
}

async function processAudioQueue() {
    while (isAudioPlaying) {
        if (audioQueue.length > 0) {
            const { audioData, config } = audioQueue.shift();
            await playAudioFromQueue(audioData, config);
        } else {
            // 队列为空时等待
            await new Promise(resolve => setTimeout(resolve, 100));
        }
    }
}

async function playAudioFromQueue(base64Audio, config) {
    return new Promise((resolve) => {
        try {
            addLog(`🔊 从队列播放音频: ${base64Audio.length}字符`, 'info');
            
            const audioData = atob(base64Audio);
            const uint8Array = new Uint8Array(audioData.length);
            
            for (let i = 0; i < audioData.length; i++) {
                uint8Array[i] = audioData.charCodeAt(i);
            }
            
            if (config.audio_format === 'float32') {
                playFloat32AudioFromQueue(uint8Array, config, resolve);
            } else {
                playPCM16AudioFromQueue(uint8Array.buffer, config, resolve);
            }
            
        } catch (error) {
            addLog('队列音频播放失败: ' + error.message, 'error');
            resolve();
        }
    });
}

function playFloat32AudioFromQueue(uint8Array, config, callback) {
    try {
        const float32Array = new Float32Array(uint8Array.buffer);
        
        const audioBuffer = audioPlaybackContext.createBuffer(
            config.channels || 1,
            float32Array.length / (config.channels || 1),
            config.sample_rate || 24000
        );
        
        for (let channel = 0; channel < (config.channels || 1); channel++) {
            const channelData = audioBuffer.getChannelData(channel);
            for (let i = 0; i < channelData.length; i++) {
                channelData[i] = float32Array[i * (config.channels || 1) + channel];
            }
        }
        
        const source = audioPlaybackContext.createBufferSource();
        source.buffer = audioBuffer;
        source.connect(audioPlaybackContext.destination);
        
        source.onended = callback;
        source.start(0);
        
        addLog(`✅ Float32队列音频播放: ${float32Array.length}样本`, 'success');
        
    } catch (error) {
        addLog('Float32队列音频播放失败: ' + error.message, 'error');
        callback();
    }
}

function playPCM16AudioFromQueue(arrayBuffer, config, callback) {
    audioPlaybackContext.decodeAudioData(arrayBuffer, function(buffer) {
        const source = audioPlaybackContext.createBufferSource();
        source.buffer = buffer;
        source.connect(audioPlaybackContext.destination);
        
        source.onended = callback;
        source.start(0);
        
        addLog(`✅ PCM16队列音频播放成功`, 'success');
    }).catch(error => {
        addLog('PCM16队列音频播放失败: ' + error.message, 'error');
        callback();
    });
}

function clearAudioQueue() {
    audioQueue = [];
    addLog('🗑️ 音频队列已清空', 'info');
}

// 添加消息到对话框
function addMessage(sender, content, type) {
    const dialogBox = document.getElementById('dialog-box');
    const messageDiv = document.createElement('div');
    messageDiv.className = `message ${type}`;
    
    messageDiv.innerHTML = `
        <span class="sender">${sender}</span>
        <span class="content">${content}</span>
    `;
    
    dialogBox.appendChild(messageDiv);
    dialogBox.scrollTop = dialogBox.scrollHeight;
}

// 清空对话
function clearDialog() {
    const dialogBox = document.getElementById('dialog-box');
    dialogBox.innerHTML = `
        <div class="message system">
            <span class="sender">系统：</span>
            <span class="content">欢迎使用豆包语音对话系统！点击下方按钮开启对话。</span>
        </div>
    `;
    
    if (ws && ws.readyState === WebSocket.OPEN) {
        ws.send(JSON.stringify({
            type: 'clear'
        }));
    }
}

// 更新状态
function updateStatus(status) {
    const statusDiv = document.getElementById('status');
    if (statusDiv) {
        statusDiv.textContent = status;
    }
    addLog(`状态更新: ${status}`, 'info');
}

// 更新最后一条AI消息
function updateLastAssistantMessage(sender, content) {
    const dialogBox = document.getElementById('dialog-box');
    const messages = dialogBox.querySelectorAll('.message.assistant');
    
    if (messages.length > 0) {
        // 获取最后一条AI消息
        const lastMessage = messages[messages.length - 1];
        const contentSpan = lastMessage.querySelector('.content');
        
        if (contentSpan) {
            contentSpan.textContent = content;
            addLog(`🔄 已更新最后一条AI消息: ${content}`, 'info');
        }
    } else {
        // 如果没有AI消息，直接添加新消息
        addMessage(sender, content, 'assistant');
        addLog(`➕ 未找到AI消息，创建新消息: ${content}`, 'info');
    }
}

// 页面加载完成后初始化
document.addEventListener('DOMContentLoaded', function() {
    addLog('页面加载完成，初始化WebSocket连接和音频队列', 'info');
    
    // 初始化音频队列
    initAudioQueue();
    
    // 初始化WebSocket连接
    initializeWebSocket();
    
    // 页面关闭时清理资源
    window.addEventListener('beforeunload', function() {
        if (isDialogActive) {
            stopDialog();
        }
        if (ws) {
            ws.close();
        }
        // 停止音频播放
        isAudioPlaying = false;
        clearAudioQueue();
    });
});

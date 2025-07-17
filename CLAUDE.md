# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Getting Started

This is a real-time voice dialogue system that connects to ByteDance's OpenSpeech API for AI voice conversations.

### Setup
```bash
# Install dependencies
pip install -r requirements.txt

# Configure API credentials in config.py
# Update X-Api-App-ID and X-Api-Access-Key with your ByteDance console credentials
```

### Running
```bash
# Start the voice dialogue system
python main.py

# System will open microphone and start conversation with AI assistant "豆包"
```

## Architecture Overview

The system uses an async event-driven architecture with three main layers:

1. **Protocol Layer** (`protocol.py`) - Custom binary protocol for WebSocket communication with gzip compression
2. **Network Layer** (`realtime_dialog_client.py`) - WebSocket client handling connection lifecycle and message formatting
3. **Audio Layer** (`audio_manager.py`) - PyAudio-based audio I/O with separate threads for recording and playback

### Key Flows

- **Audio Capture**: Microphone → PCM chunks → gzip compression → WebSocket → API
- **Audio Playback**: API response → gzip decompression → audio queue → PyAudio output stream
- **Session Management**: UUID-based sessions with StartConnection → StartSession → TaskRequest → Finish flow

### Configuration

All configuration is in `config.py`:
- WebSocket endpoint: `wss://openspeech.bytedance.com/api/v3/realtime/dialogue`
- Audio: 16kHz input, 24kHz output, mono PCM
- Bot personality: "豆包" with lively female voice

### Dependencies
- `pyaudio` - Audio I/O
- `websockets` - WebSocket client
- `asyncio` - Async runtime
- `gzip` - Message compression
- `uuid` - Session ID generation
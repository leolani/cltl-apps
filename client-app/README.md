# Client App

An audio/video-enabled client for the CLTL (Computational Lexicology & Terminology Lab) framework. This application provides voice and text-based interaction capabilities, connecting to existing CLTL conversational AI services via a distributed event bus. It includes speech recognition, voice activity detection, and a web-based chat interface.

## Table of Contents

- [Introduction](#introduction)
- [Getting Started](#getting-started)
  - [Prerequisites](#prerequisites)
  - [Installation](#installation)
  - [Running the Application](#running-the-application)
- [Application Architecture](#application-architecture)
  - [Core Components](#core-components)
  - [Event System](#event-system)
  - [Integration Model](#integration-model)
- [Configuration Guide](#configuration-guide)
- [EMISSOR Data Format](#emissor-data-format)
- [Troubleshooting](#troubleshooting)
- [Contributing](#contributing)
- [License](#license)

## Introduction

The Client App is an audio/video-enabled conversational interface designed to connect to existing CLTL-based services. It extends the capabilities of a text-only chat client by adding:

- **Voice input**: Microphone capture and automatic speech recognition (ASR)
- **Voice activity detection**: WebRTC-based detection of speech segments
- **Audio processing**: Signal capture, storage, and management
- **Hardware integration**: Direct access to system microphone and camera

Like the chat-client-app, this application focuses on **client-side functionality** and connects to external services (such as LLM-app or other CLTL conversational AI systems) through a distributed event bus (RabbitMQ). However, unlike the chat-client-app, it provides full audio/video capture and processing capabilities.

**Key features:**
- **Voice-based interaction**: Speak to conversational AI systems using your microphone
- **Automatic Speech Recognition**: Multiple ASR backends (Whisper, Google ASR, Wav2Vec, SpeechBrain)
- **Voice Activity Detection**: Automatic detection of speech segments using WebRTC VAD
- **Text-based interaction**: Web-based chat UI as alternative to voice input
- **Event bus integration**: Connects to external CLTL services via RabbitMQ
- **Context management**: Tracks conversation scenarios and speaker context
- **Multimodal data storage**: Stores audio, text, and video data using the EMISSOR framework
- **Hardware access**: Direct microphone and camera integration

**What's NOT included:**
- No language model or conversational AI logic (no LLM)
- No response generation capabilities
- No reasoning or knowledge processing

This app is designed to be a **pure audio/video client** that captures user input (voice and text) and sends it to external services, then displays their responses.

## Getting Started

### Prerequisites

For detailed installation instructions, including system-specific setup and troubleshooting, please see **[INSTALLATION.md](INSTALLATION.md)**.

#### Required: External RabbitMQ Server

The Client App requires a RabbitMQ message broker to communicate with other CLTL services. You typically connect to an existing CLTL application (like llm-app or eliza-app) that already runs RabbitMQ.

If you need to run RabbitMQ separately for testing:

```bash
docker run -d --name rabbitmq \
  -p 5672:5672 -p 15672:15672 \
  -e RABBITMQ_DEFAULT_USER=cltl \
  -e RABBITMQ_DEFAULT_PASS=cltl123 \
  rabbitmq:3.12-management
```

**Management UI**: [http://localhost:15672](http://localhost:15672) (Username: `cltl`, Password: `cltl123`)

#### System Requirements

- **Python**: 3.9 to 3.10 (required for ASR components)
- **RAM**: 4GB minimum, 8GB recommended
- **Disk Space**: ~3GB for dependencies and ASR models
- **Microphone**: System microphone or USB audio device
- **RabbitMQ**: External message broker

#### System Libraries

The following system libraries must be installed before running the application:

**macOS:**
```bash
brew install portaudio libsndfile ffmpeg
```

**Linux (Ubuntu/Debian):**
```bash
sudo apt-get install portaudio19-dev libsndfile1 ffmpeg
```

**Windows:**
See [INSTALLATION.md](INSTALLATION.md) for detailed Windows setup instructions.

### Installation

**For complete, step-by-step installation instructions with troubleshooting, see [INSTALLATION.md](INSTALLATION.md).**

**Quick Start:**

1. **Set up Python environment**

   ```bash
   cd py-app

   # Create a virtual environment
   python -m venv venv

   # Activate the virtual environment
   source venv/bin/activate  # On macOS/Linux
   # OR
   venv\Scripts\activate  # On Windows
   ```

2. **Install dependencies**

   ```bash
   pip install --upgrade pip
   pip install -r requirements.txt
   ```

   **Note:** First installation may take 10-20 minutes to download and install all CLTL components and ASR models (~150MB for Whisper base model).

3. **Configure RabbitMQ connection**

   Edit `py-app/config/default.config`:

   ```ini
   [cltl.event.kombu]
   server: amqp://cltl:cltl123@<rabbitmq-host>:5672/
   exchange: cltl.combot
   type: direct
   compression: bzip2
   ```

   Replace `<rabbitmq-host>` with the hostname or IP address of your RabbitMQ server (e.g., `localhost` if running locally).

### Running the Application

```bash
cd py-app
source venv/bin/activate     # macOS/Linux
# OR
venv\Scripts\activate        # Windows

python app.py
```

Once started, the application will:
1. Connect to RabbitMQ
2. Initialize audio devices (microphone)
3. Load ASR models (first run may take 1-5 minutes)
4. Start a conversation scenario
5. Begin listening for voice input

**Access points:**
- **Chat UI**: [http://localhost:8000/chatui/static/chat.html](http://localhost:8000/chatui/static/chat.html)
- **EMISSOR Data API**: [http://localhost:8000/emissor](http://localhost:8000/emissor)

**Usage:**
- **Voice input**: Speak into your microphone - speech will be automatically detected and transcribed
- **Text input**: Type messages in the Chat UI as an alternative to voice

Press `Ctrl+C` to stop the application.

## Application Architecture

The Client App is a full-featured audio/video client with speech processing capabilities, designed to connect to external conversational AI services.

### Core Components

#### Backend Server (`cltl-backend`)

Provides audio and video device access and signal management.

**Responsibilities:**
- Capture audio from system microphone
- Manage camera access (optional)
- Store raw audio/video signals locally
- Publish signal events to the event bus
- Provide REST API for signal access

#### Voice Activity Detection - VAD (`cltl-vad`)

Detects speech segments in audio streams using WebRTC VAD.

**Process:**
1. Subscribes to microphone audio events
2. Analyzes audio data to detect voice activity
3. Publishes voice activity events with temporal annotations

**Configuration:**
- Activity window, threshold, gap allowance, and padding are configurable
- Optimized for conversational speech detection

#### Automatic Speech Recognition - ASR (`cltl-asr`)

Transcribes detected speech to text.

**Process:**
1. Subscribes to voice activity events
2. Retrieves audio segments from storage
3. Transcribes audio to text using configured ASR backend
4. Publishes text signal events

**Supported Implementations:**
- **Whisper**: OpenAI's Whisper model (default, recommended)
- **Google ASR**: Google Cloud Speech-to-Text
- **Wav2Vec**: Facebook's Wav2Vec2 model
- **SpeechBrain**: SpeechBrain transformer models

#### Chat UI (`cltl-chat-ui`)

Web-based chat interface for text interaction.

**Responsibilities:**
- Display conversation history
- Accept user text input (alternative to voice)
- Show responses from external services
- Publish text messages to the event bus
- Subscribe to response messages

#### Context Service (`app-service/context`)

Manages conversation context and state.

**Responsibilities:**
- Create and manage conversation scenarios
- Track speaker identity
- Publish scenario lifecycle events (start/stop)
- Maintain conversation metadata

#### EMISSOR Data Storage (`cltl-emissor-data`)

Stores multimodal conversation data using the EMISSOR framework.

**Responsibilities:**
- Persist audio signals (microphone recordings)
- Persist text signals (transcriptions and responses)
- Store scenario metadata
- Provide REST API for accessing stored data
- Log all events for audit and analysis

#### BDI Service (`cltl-bdi`)

Belief-Desire-Intention reasoning system for managing application state.

**Process:**
- Tracks application intentions (init → chat → quit)
- Responds to keyword-based triggers
- Manages conversation lifecycle

#### Keyword Service (`cltl-keyword`)

Extracts intentions from user text.

**Process:**
- Analyzes user messages for keywords
- Publishes intention events based on detected keywords
- Supports conversation flow control

### Event System

The Client App communicates with external services through RabbitMQ using a publish-subscribe pattern.

#### Key Event Topics

| Topic | Client App Role | Purpose |
|-------|----------------|---------|
| `cltl.topic.microphone` | **Publisher** | Raw audio from microphone |
| `cltl.topic.vad` | **Publisher** | Voice activity detection events |
| `cltl.topic.text_in` | **Publisher** | Transcribed speech and typed messages |
| `cltl.topic.text_out` | **Subscriber** | Responses from external services |
| `cltl.topic.scenario` | Publisher | Scenario lifecycle events |
| `cltl.topic.intention` | Subscriber | Intention events from BDI |
| `cltl.topic.desire` | Publisher | Desire events to BDI |

### Integration Model

```
┌─────────────────────────────────────────────────────────┐
│                   RabbitMQ Event Bus                     │
│                   (External Service)                     │
└─────────────────────────────────────────────────────────┘
          │                           │
          │ cltl.topic.text_in        │ cltl.topic.text_out
          │ (transcribed speech)      │ (responses)
          ▼                           │
┌─────────────────────────────────────▼───────────────────┐
│              Client App (This App)                       │
│  ┌──────────────────────────────────────────────────┐   │
│  │  Microphone → Backend → Audio Signal             │   │
│  │         ↓                                         │   │
│  │      VAD → Voice Activity Detection              │   │
│  │         ↓                                         │   │
│  │      ASR → Speech-to-Text Transcription          │   │
│  │         ↓                                         │   │
│  │   Text Signal Published to Event Bus             │   │
│  └──────────────────────────────────────────────────┘   │
│  ┌──────────────────────────────────────────────────┐   │
│  │  Chat UI (http://localhost:8000/chatui)          │   │
│  │  - User can type messages (alternative input)    │   │
│  │  - Displays responses from external service      │   │
│  └──────────────────────────────────────────────────┘   │
│  ┌──────────────────────────────────────────────────┐   │
│  │  Context Service                                  │   │
│  │  - Manages scenarios and conversation state      │   │
│  └──────────────────────────────────────────────────┘   │
│  ┌──────────────────────────────────────────────────┐   │
│  │  EMISSOR Data Storage                             │   │
│  │  - Archives audio, text, and conversation data   │   │
│  └──────────────────────────────────────────────────┘   │
└──────────────────────────────────────────────────────────┘

┌─────────────────────────────────────────────────────────┐
│      External CLTL Service (Separate Application)        │
│  - Subscribes to cltl.topic.text_in                     │
│  - Processes messages (LLM, ELIZA, custom logic, etc.)  │
│  - Publishes responses to cltl.topic.text_out          │
└─────────────────────────────────────────────────────────┘
```

### Conversation Flow

**Voice Input Flow:**
1. **User speaks** → Microphone captures audio
2. **Backend publishes audio signal** to `cltl.topic.microphone` (via RabbitMQ)
3. **VAD detects speech activity** → publishes to `cltl.topic.vad`
4. **ASR transcribes audio** → publishes text to `cltl.topic.text_in`
5. **External service receives text** (listens on `cltl.topic.text_in`)
6. **External service processes** (using LLM, ELIZA, or custom logic)
7. **External service publishes response** to `cltl.topic.text_out` (via RabbitMQ)
8. **Client App receives response** (subscribes to `cltl.topic.text_out`)
9. **Chat UI displays response** to user
10. **EMISSOR Data Storage archives** all audio and text signals

**Text Input Flow (Alternative):**
1. **User types message** in Chat UI
2. **Chat UI publishes** to `cltl.topic.text_in` (via RabbitMQ)
3. **External service processes** and publishes response to `cltl.topic.text_out`
4. **Chat UI displays response**
5. **EMISSOR Data Storage archives** conversation

The Client App is agnostic to how messages are processed - it only handles audio/video capture, speech recognition, and display of responses.

## Configuration Guide

Configuration is managed through INI-style files in `py-app/config/`.

### Key Configuration Sections

#### Event Bus Configuration

```ini
[cltl.event]
implementation: kombu   # Always use Kombu (RabbitMQ) for distributed messaging

[cltl.event.kombu]
server: amqp://cltl:cltl123@localhost:5672/
exchange: cltl.combot
type: direct
compression: bzip2
```

**Configuration for different RabbitMQ locations:**
- **RabbitMQ on localhost**: `amqp://cltl:cltl123@localhost:5672/`
- **RabbitMQ on remote server**: `amqp://cltl:cltl123@192.168.1.100:5672/`

#### Audio Configuration

```ini
[cltl.audio]
sampling_rate: 16000        # Audio sampling rate in Hz (16 kHz for speech)
channels: 1                 # Number of audio channels (1=mono)
sample_depth: 2            # Bytes per sample (2=16-bit)
frame_size: 480            # Audio frame size in samples

[cltl.backend.mic]
topic: cltl.topic.microphone    # Enable microphone (empty to disable)
```

#### Voice Activity Detection Configuration

```ini
[cltl.vad]
implementation: webrtc          # VAD implementation (webrtc, or empty to disable)
mic_topic: cltl.topic.microphone
vad_topic: cltl.topic.vad

[cltl.vad.webrtc]
activity_window: 300           # Window size for activity detection (ms)
activity_threshold: 0.8        # Threshold for voice detection (0.0-1.0)
allow_gap: 300                 # Maximum gap between speech segments (ms)
padding: 600                   # Padding around detected speech (ms)
```

#### ASR Configuration

```ini
[cltl.asr]
implementation: whisper         # ASR implementation: whisper, google, speechbrain, wav2vec
sampling_rate: 16000           # Must match [cltl.audio] sampling_rate
vad_topic: cltl.topic.vad
asr_topic: cltl.topic.text_in

[cltl.asr.whisper]
model: base                    # Model size: tiny, base, small, medium, large
language: en                   # Language code
```

**ASR Model Selection:**
- `tiny`: Fastest, least accurate (~75MB)
- `base`: Good balance (default, ~150MB)
- `small`: Better accuracy (~500MB)
- `medium`: High accuracy (~1.5GB)
- `large`: Best accuracy (~3GB)

#### Chat UI Configuration

```ini
[cltl.chat-ui]
name: chat-ui
agent_id: leolani
external_input: True    # Allow external text input
timeout: 0              # No timeout for user input

[cltl.chat-ui.events]
local: True
topic_utterance: cltl.topic.text_in      # Where to publish user messages
topic_response: cltl.topic.text_out      # Where to receive responses
topic_scenario: cltl.topic.scenario      # Scenario management
```

#### EMISSOR Data Configuration

```ini
[cltl.emissor-data]
path: ./storage/emissor

[cltl.emissor-data.event]
topics: cltl.topic.scenario, cltl.topic.image, cltl.topic.microphone,
        cltl.topic.text_in, cltl.topic.text_out, cltl.topic.vad,
        cltl.desire, cltl.intention
```

For detailed configuration options, see `py-app/config/default.config`.

## EMISSOR Data Format

### What is EMISSOR?

**EMISSOR** stands for **E**pisodic **M**emories and **I**nterpretations with **S**ituated **S**cenario-based **O**ntological **R**eferences.

EMISSOR is a framework for representing multimodal interaction data with explicit temporal, spatial, and ontological grounding.

### Data Structure

#### Scenarios

A **scenario** represents a complete conversation session. Each scenario is stored as a folder in `py-app/storage/emissor/`:

```
scenario-name/
├── scenario-name.json        # Scenario metadata and context
├── audio.json               # Audio signal metadata and annotations
├── text.json                # Text signal metadata and annotations
├── image.json               # Image signal metadata (if camera enabled)
├── audio/                   # Audio files (.wav)
├── text/                    # Text files (.csv)
└── image/                   # Image files (.jpg, .png)
```

**Stored Data:**
- **Audio signals**: Raw microphone recordings
- **Text signals**: Transcriptions and responses
- **VAD annotations**: Speech activity timestamps
- **Scenario metadata**: Participants, location, timestamps

#### Storage and Access

The EMISSOR Data Service provides a REST API at: [http://localhost:8000/emissor](http://localhost:8000/emissor)

**Key Endpoints:**
- `GET /scenarios` - List all scenarios
- `GET /scenarios/{id}` - Get scenario metadata
- `GET /scenarios/{id}/signals/audio` - Get audio signals for a scenario
- `GET /scenarios/{id}/signals/text` - Get text signals for a scenario

For more details on the EMISSOR data format, see the [EMISSOR documentation](https://github.com/leolani/emissor).

## Troubleshooting

### Installation Issues

For comprehensive installation troubleshooting, see **[INSTALLATION.md](INSTALLATION.md)**.

**Common issues:**
- **Compiler errors**: Install build tools (Xcode Command Line Tools on macOS, build-essential on Linux)
- **Rust compiler errors**: Install Rust from [rustup.rs](https://rustup.rs/)
- **Audio library errors**: Install PortAudio and libsndfile system libraries

### Runtime Issues

**Problem:** Cannot connect to RabbitMQ

```bash
# Verify RabbitMQ is running
docker ps | grep rabbitmq

# Check RabbitMQ logs
docker logs rabbitmq

# Test connection
telnet localhost 5672
```

**Solution:**
- Ensure RabbitMQ is running and accessible
- Verify `server` configuration in `config/default.config` matches RabbitMQ location
- Check firewall settings if connecting to remote RabbitMQ

**Problem:** Microphone not working

**Solution:**
- Check system microphone permissions
- Verify microphone is selected as default input device
- Test microphone with system audio settings
- On macOS: Grant Terminal/IDE microphone access in System Preferences → Security & Privacy

**Problem:** No voice detection (VAD not triggering)

**Solution:**
- Speak louder or closer to microphone
- Adjust `activity_threshold` in `[cltl.vad.webrtc]` (lower value = more sensitive)
- Check microphone levels in system audio settings
- Verify VAD is enabled: `[cltl.vad] implementation: webrtc`

**Problem:** ASR not transcribing correctly

**Solution:**
- Use larger Whisper model for better accuracy (`small` or `medium`)
- Ensure quiet environment (minimize background noise)
- Speak clearly and at moderate pace
- Check audio quality with `storage/audio/` recordings

**Problem:** No responses from external service

**Possible causes:**
1. No external service is listening on `cltl.topic.text_in`
2. External service is not publishing to `cltl.topic.text_out`
3. RabbitMQ exchange/topic mismatch

**Solution:**
- Check RabbitMQ Management UI to verify messages are being published
- Ensure external service (e.g., llm-app) is connected to same RabbitMQ instance
- Verify topic names match between client and external service
- Check logs for both services

**Problem:** ASR models downloading slowly

First run downloads Whisper models from Hugging Face. This can take 2-10 minutes depending on your connection. Models are cached in `~/.cache/huggingface/` for subsequent runs.

**Problem:** Out of memory during ASR

**Solution:**
- Use smaller Whisper model (`tiny` or `base` instead of `medium` or `large`)
- Close other memory-intensive applications
- Ensure system has sufficient RAM (8GB recommended)

### Getting Help

1. Check logs in `py-app/storage/event_log/`
2. Enable debug logging in `config/logging.config`
3. Review [INSTALLATION.md](INSTALLATION.md) for detailed setup instructions
4. Review [cltl-combot documentation](https://github.com/leolani/cltl-combot)
5. Check RabbitMQ Management UI for message flow
6. Open an issue on the relevant GitHub repository

## Contributing

Contributions are welcome! To contribute:

1. Fork the Project
2. Create your Feature Branch (`git checkout -b feature/AmazingFeature`)
3. Make your changes
4. Commit your Changes (`git commit -m 'Add some AmazingFeature'`)
5. Push to the Branch (`git push origin feature/AmazingFeature`)
6. Open a Pull Request

### Guidelines

- Follow the coding conventions in [CLAUDE.md](CLAUDE.md)
- Write clean, documented code following Clean Code principles
- Add tests for new functionality
- Update documentation as needed

For detailed development workflows, see the [cltl-combot](https://github.com/leolani/cltl-combot) documentation.

## License

Distributed under the MIT License. See [LICENSE](py-app/LICENSE) for more information.

## Authors

- [Taewoon Kim](https://tae898.github.io/)
- [Thomas Baier](https://www.linkedin.com/in/thomas-baier-05519030/)
- [Selene Báez Santamaría](https://selbaez.github.io/)
- [Piek Vossen](https://github.com/piekvossen)

## References

For more information about the CLTL framework and related projects:

- [CLTL Combot Framework](https://github.com/leolani/cltl-combot)
- [CLTL Backend](https://github.com/leolani/cltl-backend)
- [CLTL ASR](https://github.com/leolani/cltl-asr)
- [CLTL VAD](https://github.com/leolani/cltl-vad)
- [EMISSOR Framework](https://github.com/leolani/emissor)
- [Leolani Platform](https://github.com/leolani)

### Academic Publications

If you use the Client App or EMISSOR framework in your research, please cite:

```bibtex
@inproceedings{emissor:2021,
    title = {EMISSOR: A platform for capturing multimodal interactions as Episodic Memories and Interpretations with Situated Scenario-based Ontological References},
    author = {Selene Baez Santamaria and Thomas Baier and Taewoon Kim and Lea Krause and Jaap Kruijt and Piek Vossen},
    url = {https://mmsr-workshop.github.io/programme},
    booktitle = {Proceedings of the MMSR workshop "Beyond Language: Multimodal Semantic Representations", IWSC2021},
    year = {2021}
}
```

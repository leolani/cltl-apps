# LLM App

A conversational AI application built using the CLTL (Computational Lexicology & Terminology Lab) framework, powered by Large Language Models (LLMs) with support for voice and text input through a modular, event-driven architecture.

## Table of Contents

- [Introduction](#introduction)
- [Getting Started](#getting-started)
  - [Installation](#installation)
  - [Running the Application](#running-the-application)
- [Advanced Setup](#advanced-setup)
- [Application Architecture](#application-architecture)
  - [Core Components](#core-components)
  - [Event System](#event-system)
  - [Data Flow](#data-flow)
- [Event Bus: Local vs Distributed](#event-bus-local-vs-distributed)
- [EMISSOR Data Format](#emissor-data-format)
- [Configuration Guide](#configuration-guide)
- [Prerequisites](#prerequisites)
- [Troubleshooting](#troubleshooting)
- [Contributing](#contributing)
- [License](#license)

## Introduction

The LLM App is a conversational AI system that demonstrates the CLTL framework's modular approach to building interactive agents. The application is powered by Large Language Models (LLMs) including Llama and Qwen, providing sophisticated conversational capabilities with modern speech recognition and multimodal interaction support.

**Key features:**
- **LLM-powered conversations**: Leverage state-of-the-art language models (Llama, Qwen, and other compatible models) for natural, context-aware interactions
- **Voice-based interaction** using Automatic Speech Recognition (ASR)
- **Text-based interaction** through a web chat interface
- **Modular, event-driven architecture** with pluggable components
- **Multimodal data storage** using the EMISSOR framework
- **Multiple ASR implementations**: Whisper, Google ASR, Wav2Vec, SpeechBrain
- **Flexible deployment**: local Python app or Docker Compose with RabbitMQ
- **Two event bus implementations**: in-memory synchronous or RabbitMQ-based distributed
- **Configurable LLM settings**: customize model selection, temperature, instruction prompts, and conversation history

The application serves as a blueprint for building LLM-powered conversational agents within the CLTL framework and can be extended with additional components for more sophisticated interactions.

## Getting Started

### Installation

Before installing, ensure you have the required [prerequisites](#prerequisites).

### LLM Configuration
MacOS and Linux users can use any LLM that's available via Ollama. Check the "tags" section under the model page you
want to use on https://ollama.ai/library and write the tag for the value of the environment variable `LLM=` in the `.env` file.
All platforms can use GPT-3.5-turbo and GPT-4 (bring your own API keys for OpenAI models).

**MacOS**
Install [Ollama](https://ollama.ai) on MacOS and start it before running `docker compose up` using `ollama serve` in a separate terminal.
Make sure to set the `OLLAMA_BASE_URL=http://host.docker.internal:11434` in the `.env` file when using Ollama docker container.

**Linux**
No need to install Ollama manually, it will run in a container as
part of the stack when running with the _server_ profile: run `docker compose up`.

To use the _server-gpu_ profile: run `docker compose --profile server-gpu up`. Also change `OLLAMA_BASE_URL=http://llm-gpu:11434` in the `.env` file.

#### LLM Model Setup

The application requires a compatible LLM model file. You have two options:

**Option 1: Use a Local Model (Recommended for Development)**

Download a quantized Llama model from HuggingFace:

1. Visit the [QuantFactory repository on HuggingFace](https://huggingface.co/QuantFactory)
2. Download a quantized model (e.g., `Meta-Llama-3-8B-Instruct.Q2_K.gguf`)
3. Create a `models` directory in `py-app/`:
   ```bash
   mkdir -p py-app/models
   ```
4. Place the downloaded model file in `py-app/models/`
5. Update `py-app/config/default.config` to reference your model:
   ```ini
   [cltl.llm]
   model: ./models/Meta-Llama-3-8B-Instruct.Q2_K.gguf
   ```

**Option 2: Use Ollama (Recommended for Production)**

Alternatively, you can use [Ollama](https://ollama.ai/) to manage models:

1. Install Ollama following their [installation instructions](https://ollama.ai/download)
2. Pull a model:
   ```bash
   ollama pull llama3.2
   # or
   ollama pull qwen2.5
   ```
3. Configure the application to use Ollama by setting the model name in `py-app/config/default.config`:
   ```ini
   [cltl.llm]
   model: llama3.2
   ```

The application will automatically detect if you're using a local model file (`.gguf` extension) or an Ollama model (model name without extension).

#### Option 1: Local Python Application (Recommended for Development)

1. **Set Up Python Environment**

```bash
cd py-app

# Create a virtual environment
python -m venv venv

# Activate the virtual environment
source venv/bin/activate  # On macOS/Linux
# OR
venv\Scripts\activate  # On Windows
```

2. **Install Dependencies**

```bash
pip install --upgrade pip
pip install -r requirements.txt
```

This will install all CLTL components directly from their GitHub repositories at specific commit versions, ensuring consistency and reproducibility.

**Note:** The first installation can take 10-20 minutes as it downloads and compiles various dependencies including machine learning models and audio libraries.

#### Option 2: Docker Compose (Recommended for Production)

**Build and Run with Docker Compose**

```bash
cd docker-app
docker-compose up --build
```

This will:
- Start a RabbitMQ message broker
- Build and start the LLM application container
- Set up networking between services

### Running the Application

#### Local Python Application

This mode uses an **in-memory SynchronousEventBus** for component communication, which is ideal for development and debugging.

```bash
cd py-app

# Activate virtual environment
source venv/bin/activate     # macOS/Linux
# OR
venv\Scripts\activate        # Windows

python app.py
```

The application will start initializing components. You may see connection warnings initially - these can be ignored as services start up. First-time execution may take several minutes as ASR models are downloaded.

Once fully started, the application will greet you. You can interact via:
- **Web Chat UI**: [http://localhost:8000/chatui/static/chat.html](http://localhost:8000/chatui/static/chat.html)
- **Voice**: Speak into your microphone (when ASR is configured)

Additional endpoints:
- **Storage API**: [http://localhost:8000/storage](http://localhost:8000/storage)
- **EMISSOR Data API**: [http://localhost:8000/emissor](http://localhost:8000/emissor)

Press `Ctrl+C` to stop the application.

#### Docker Compose Application

This mode uses **RabbitMQ with the Kombu event bus** for distributed component communication, ideal for production deployments.

The Docker setup supports two modes: **text-only** (default) or **with voice input** (requires backend on host).

##### Quick Start (Text-Only Mode)

```bash
cd docker-app
docker-compose up
```

Use `docker-compose up --build` to rebuild after code or configuration changes.

**Access points:**
- **Chat UI**: [http://localhost:8000/chatui/static/chat.html](http://localhost:8000/chatui/static/chat.html)
- **RabbitMQ Management UI**: [http://localhost:15672](http://localhost:15672) (Username: `eliza`, Password: `eliza123`)
- **Storage API**: [http://localhost:8000/storage](http://localhost:8000/storage)
- **EMISSOR Data API**: [http://localhost:8000/emissor](http://localhost:8000/emissor)

By default, the application runs in text-only mode. Interact via the Chat UI - no voice setup needed.

##### Enabling Voice Input

To enable voice interaction, you need to run a backend server on your host machine and activate the voice configuration.

**Step 1: Run the backend server on your host**

```bash
# Create and activate a virtual environment
python -m venv backend-venv
source backend-venv/bin/activate     # macOS/Linux; use backend-venv\Scripts\activate on Windows

# Install the backend
pip install cltl.backend[host]

# Start the backend server
leoserv --rate 16000 --channels 1 --port 8000
```

**Note:** The `leoserv` arguments must match your application configuration (see [Configuration Guide](#configuration-guide)).

**Step 2: Activate voice configuration**

```bash
cd docker-app/config
cp custom.voice.config custom.config
```

This enables the microphone, VAD (Voice Activity Detection), and ASR (Automatic Speech Recognition).

**Step 3: Start Docker**

```bash
cd docker-app
docker-compose up --build
```

The Docker container connects to the host backend via `host.docker.internal:8000`.

##### Management Commands

```bash
docker-compose down              # Stop services
docker-compose logs -f           # View logs
docker-compose ps                # Check status
```

## Advanced Setup

### Running Local Python App with External RabbitMQ

For development and debugging, you may want to run the Python application locally while using RabbitMQ for distributed messaging. This gives you the benefits of the Kombu event bus (message persistence, monitoring) while allowing easy debugging of the application code.

**Step 1: Start RabbitMQ standalone**

```bash
docker run -d --name rabbitmq \
  -p 5672:5672 -p 15672:15672 \
  -e RABBITMQ_DEFAULT_USER=eliza \
  -e RABBITMQ_DEFAULT_PASS=eliza123 \
  rabbitmq:3.12-management
```

**Step 2: Configure the application to use localhost RabbitMQ**

Edit `py-app/config/default.config` and update the Kombu server setting:

```ini
[cltl.event.kombu]
server: amqp://eliza:eliza123@localhost:5672/
exchange: cltl.combot
type: direct
compression: bzip2
```

Also ensure the event implementation is set to use Kombu:

```ini
[cltl.event]
implementation: kombu
```

**Step 3: Run the application**

```bash
cd py-app
source venv/bin/activate     # macOS/Linux
# OR
venv\Scripts\activate        # Windows

python app.py
```

**Access points:**
- **Application**: [http://localhost:8000/chatui/static/chat.html](http://localhost:8000/chatui/static/chat.html)
- **RabbitMQ Management UI**: [http://localhost:15672](http://localhost:15672) (Username: `eliza`, Password: `eliza123`)

**Benefits of this setup:**
- Local debugging with breakpoints while using distributed messaging
- Monitor message flow via RabbitMQ Management UI
- Test Kombu integration without full Docker setup
- Component isolation with message persistence

**To stop RabbitMQ:**

```bash
docker stop rabbitmq
docker rm rabbitmq
```

## Application Architecture

The LLM App follows a modular, event-driven architecture where components communicate through an event bus. This design enables loose coupling, extensibility, and flexible deployment options.

![LLM App Architecture](doc/LLMCombot.png)

### Core Components

#### Backend Server (`cltl-backend`)

Provides REST API endpoints for raw audio and video signals and manages device access.

**Responsibilities:**
- Expose microphone and camera through REST API
- Manage signal resources (e.g., mute microphone while speaking)
- Store raw signal data in local storage
- Publish events for incoming signals with storage references

**Storage Paths:**
- Audio: `py-app/storage/audio/`
- Images: `py-app/storage/image/`

#### Voice Activity Detection - VAD (`cltl-vad`)

Detects speech segments in audio streams using WebRTC VAD.

**Process:**
1. Subscribes to audio signal events from the backend
2. Analyzes audio data to detect voice activity
3. Publishes voice activity events with temporal annotations (mentions)

#### Automatic Speech Recognition - ASR (`cltl-asr`)

Transcribes detected speech to text.

**Process:**
1. Subscribes to voice activity events
2. Retrieves referenced audio segments
3. Transcribes audio to text
4. Publishes text signal events linked to audio segments

**Supported Implementations:**
- **Whisper**: OpenAI's Whisper model (recommended)
- **Google ASR**: Google Cloud Speech-to-Text
- **Wav2Vec**: Facebook's Wav2Vec2 model
- **SpeechBrain**: SpeechBrain transformer models

#### LLM Module (`cltl-llm`)

Core conversational logic powered by Large Language Models for natural, context-aware dialogue generation.

**Process:**
1. Subscribes to text signal events (non-robot speaker)
2. Processes input text using the configured LLM (Llama, Qwen, or other compatible models)
3. Maintains conversation history for context-aware responses
4. Publishes response text signal events (robot speaker)

**Supported Models:**
- **Llama**: Meta's Llama models (e.g., Llama 3.2, Llama 3-8B-Instruct)
- **Qwen**: Alibaba's Qwen models (e.g., Qwen 2.5)
- **Other GGUF models**: Any compatible quantized model from HuggingFace
- **Ollama models**: Models managed through the Ollama platform

**Configuration Options:**
- **model**: Model name or path to local `.gguf` file
- **instruction**: System prompt to guide the LLM's behavior
- **intro**: Initial greeting message
- **stop**: Farewell message
- **temperature**: Controls response randomness (0.0-2.0)
- **max_history**: Number of conversation turns to maintain in context

#### Chat UI (`cltl-chat-ui`)

Web-based chat interface for text interaction displaying conversation history and agent responses.

#### Context Service (`cltl-context`)

Manages conversation context and maintains state across interactions, tracking scenarios, speaker context, and intention/desire states.

#### EMISSOR Data Storage (`cltl-emissor-data`)

Stores multimodal interaction data using the EMISSOR framework, persisting scenarios with temporal/spatial grounding, signals, and annotations.

### Event System

Components communicate via an event bus that publishes and subscribes to typed events on named topics.

#### Key Event Topics

| Topic | Publisher | Subscriber | Payload |
|-------|-----------|------------|---------|
| `cltl.topic.microphone` | Backend | VAD | Audio signal events |
| `cltl.topic.vad` | VAD | ASR | Voice activity mentions |
| `cltl.topic.text_in` | ASR, Chat UI | LLM | Text signals (user) |
| `cltl.topic.text_out` | LLM | Chat UI, Backend | Text signals (robot) |
| `cltl.topic.scenario` | Context | Multiple | Scenario state changes |
| `cltl.topic.intention` | BDI, Keywords | Multiple | Intention events |
| `cltl.topic.desire` | Multiple | BDI | Desire events |

### Data Flow

Here's a typical conversation flow:

```
1. User speaks → Microphone captures audio
2. Backend Container → Stores audio, publishes audio signal event
3. VAD → Detects speech, publishes voice activity mention
4. ASR → Transcribes speech, publishes text signal event
5. LLM → Processes text with conversation context, generates response using the language model
6. Chat UI → Displays response to user
7. EMISSOR Data → Logs all events and signals
```

For text-only interaction (via Chat UI):

```
1. User types message in Chat UI
2. Chat UI → Publishes text signal event
3. LLM → Processes text with conversation history, generates context-aware response
4. Chat UI → Displays response
5. EMISSOR Data → Logs conversation
```

## Event Bus: Local vs Distributed

The LLM App supports two event bus implementations, each suited for different deployment scenarios:

### SynchronousEventBus (Local Python App)

**Used in:** `py-app` directory when running locally

**Characteristics:**
- **In-process communication**: Direct method calls within a single Python process
- **Synchronous execution**: Event handlers execute immediately in the publishing thread
- **No external dependencies**: No message broker or infrastructure required
- **Simple debugging**: All components run in one process, easy to debug with breakpoints
- **Fast performance**: No serialization or network overhead

**Best for:**
- Development and debugging
- Single-machine deployments
- Testing and experimentation
- Scenarios where all components have compatible Python requirements

**Configuration:** Default in `py-app/config/default.config` (no Kombu section needed)

### Kombu EventBus with RabbitMQ (Docker Compose)

**Used in:** `docker-app` directory with Docker Compose

**Characteristics:**
- **Distributed communication**: Messages pass through RabbitMQ message broker
- **Asynchronous execution**: Event handlers run independently, can be on different machines
- **Message persistence**: Messages can survive application restarts
- **Scalability**: Components can run on separate containers/machines
- **Monitoring**: RabbitMQ Management UI provides visibility into message flow
- **Production-ready**: Suitable for production deployments with high reliability needs

**Best for:**
- Production deployments
- Distributed architectures
- Scalable systems
- Environments where components need isolation
- Scenarios requiring message monitoring and reliability

**Configuration:** Configured in `docker-app/docker-compose.yml` and app configuration:

```ini
[cltl.event.kombu]
server: amqp://eliza:eliza123@rabbitmq:5672/
exchange: cltl.combot
type: direct
compression: bzip2
```

**Trade-offs:**

| Aspect | SynchronousEventBus | Kombu + RabbitMQ |
|--------|---------------------|------------------|
| Setup Complexity | Simple | Requires RabbitMQ |
| Performance | Fastest | Network overhead |
| Debugging | Easy | More complex |
| Scalability | Single machine | Multi-machine |
| Monitoring | Limited | RabbitMQ UI |
| Reliability | In-memory only | Persistent messages |

## EMISSOR Data Format

### What is EMISSOR?

**EMISSOR** stands for **E**pisodic **M**emories and **I**nterpretations with **S**ituated **S**cenario-based **O**ntological **R**eferences.

EMISSOR is a comprehensive framework for representing multimodal interaction data with explicit grounding to temporal containers (when), spatial containers (where), and ontological references (what entities are involved).

### Data Structure

#### Scenarios

A **scenario** represents a complete interaction episode. Each scenario is stored as a folder in `py-app/storage/emissor/` containing:

```
scenario-name/
├── scenario-name.json        # Scenario metadata and context
├── audio.json               # Audio signal metadata and annotations
├── text.json                # Text signal metadata and annotations
├── image.json               # Image signal metadata and annotations
├── audio/                   # Audio files (.wav)
├── text/                    # Text files (.csv)
└── image/                   # Image files (.jpg, .png)
```

#### Storage and Access

The EMISSOR Data Service provides a REST API at: [http://localhost:8000/emissor](http://localhost:8000/emissor)

**Key Endpoints:**
- `GET /scenarios`: List all scenarios
- `GET /scenarios/{id}`: Get scenario metadata
- `GET /scenarios/{id}/signals/{modality}`: Get signals for a modality

For more details on the EMISSOR data format, see the [EMISSOR documentation](https://github.com/leolani/emissor).

## Configuration Guide

Configuration is managed through INI-style files in `py-app/config/`:
- `default.config`: Main application configuration
- `logging.config`: Python logging configuration

### Key Configuration Sections

#### Audio Configuration

```ini
[cltl.audio]
sampling_rate: 16000        # Audio sampling rate in Hz
channels: 1                 # Number of audio channels (1=mono)
sample_depth: 2            # Bytes per sample (2=16-bit)
frame_size: 480            # Audio frame size in samples
```

#### ASR Configuration

```ini
[cltl.asr]
implementation: whisper     # ASR implementation: whisper, google, speechbrain, wav2vec
sampling_rate: 16000        # Must match [cltl.audio] sampling_rate
vad_topic: cltl.topic.vad   # Topic to subscribe for voice activity
asr_topic: cltl.topic.text_in  # Topic to publish transcriptions

[cltl.asr.whisper]
model: base                 # Model size: tiny, base, small, medium, large
language: en                # Language code
```

#### LLM Configuration

The LLM module is the core component that powers the conversational capabilities:

```ini
[cltl.llm]
# Model configuration - use either a local .gguf file or an Ollama model name
model: llama3.2                    # Model name (for Ollama) or path to .gguf file
# model: ./models/Meta-Llama-3-8B-Instruct.Q2_K.gguf  # Alternative: local model path

# Optional: External LLM server configuration (uncomment to use)
# server                           # Enable external server mode
# port: 9001                       # Port for external LLM server

# System prompt to guide the LLM's behavior
instruction: "You are a medical robot. You will have an extensive conversation with an elderly person. You first ask for his or her name and you address the person with his or her name. Answer in short sentences with no more than 15 words."

# Initial greeting when conversation starts
intro: "Hi, I am Leolani and I want to help you. I listen to what you tell me and give medical advice. Tell be about yourself. Who are you?"

# Farewell message when conversation ends
stop: "It was great talking to you. See you soon!"

# Temperature controls randomness (0.0 = deterministic, 2.0 = very creative)
temperature: 0.9

# Number of conversation turns to maintain in context
max_history: 15

# Event topics for integration
topic_input: cltl.topic.text_in    # Topic to subscribe for user messages
topic_output: cltl.topic.text_out  # Topic to publish LLM responses
topic_scenario: cltl.topic.scenario # Topic for scenario management
```

**Configuration Options Explained:**

- **model**: Can be either:
  - An Ollama model name (e.g., `llama3.2`, `qwen2.5`)
  - A path to a local `.gguf` file (e.g., `./models/Meta-Llama-3-8B-Instruct.Q2_K.gguf`)

- **server/port**: (Optional) Use an external LLM server instead of loading the model locally. Uncomment these lines to enable.

- **instruction**: The system prompt that defines the LLM's role and behavior. Customize this to create different personas or capabilities.

- **intro**: The first message users see when starting a conversation.

- **stop**: The message displayed when ending a conversation.

- **temperature**: Controls response creativity:
  - `0.0-0.3`: More focused and deterministic
  - `0.7-1.0`: Balanced creativity and coherence (recommended)
  - `1.5-2.0`: More creative but potentially less coherent

- **max_history**: Number of previous conversation turns to include in the LLM context. Higher values provide more context but use more memory.

#### Event Bus Configuration (Docker only)

For the Docker Compose deployment, RabbitMQ configuration is in `docker-app/docker-compose.yml`:

```yaml
rabbitmq:
  image: "rabbitmq:3.12-management"
  environment:
    - RABBITMQ_DEFAULT_USER=eliza
    - RABBITMQ_DEFAULT_PASS=eliza123
```

And referenced in the app config:

```ini
[cltl.event.kombu]
server: amqp://eliza:eliza123@rabbitmq:5672/
exchange: cltl.combot
type: direct
compression: bzip2
```

For detailed configuration options, see `py-app/config/default.config`.

## Prerequisites

This section lists the system requirements for running the LLM App. These prerequisites are referenced in the [Installation](#installation) section.

### Python

Python version **3.8 to 3.10** is required. Verify your Python version:

```bash
python --version
which python
```

#### macOS
To install Python 3.10 on macOS using Homebrew:

```bash
brew install python@3.10
export PATH="$(brew --prefix)/opt/python@3.10/libexec/bin:$PATH"
```

Add the export line to your `~/.zshrc` (or `~/.bashrc` for bash) to make it permanent.

#### Linux
```bash
# Ubuntu/Debian
sudo apt-get update
sudo apt-get install python3.10 python3.10-venv python3-pip

# Fedora/RHEL
sudo dnf install python3.10
```

#### Windows
Download and install Python 3.10 from [python.org](https://www.python.org/downloads/). During installation, make sure to check "Add Python to PATH".

**Note:** Avoid using Anaconda as it can cause dependency conflicts with pip installations.

### System Libraries

#### Audio Libraries

Audio processing requires several system libraries:

```bash
# macOS
brew install portaudio libsndfile ffmpeg

# Ubuntu/Debian
sudo apt-get install portaudio19-dev libsndfile1 ffmpeg

# Fedora/RHEL
sudo dnf install portaudio-devel libsndfile ffmpeg

# Windows
# Install via conda (if needed) or download pre-built binaries
# For most users, pip will handle Windows dependencies automatically
```

If you encounter issues with libsndfile on macOS, add this to your `~/.zshrc`:

```bash
export DYLD_LIBRARY_PATH="/opt/homebrew/lib:$DYLD_LIBRARY_PATH"
```

#### Compiler Requirements

Some Python dependencies require C and Rust compilers:

**macOS:**
```bash
# Install Xcode Command Line Tools
sudo xcode-select --install
```

**Linux:**
```bash
# Ubuntu/Debian
sudo apt-get install build-essential

# Fedora/RHEL
sudo dnf groupinstall "Development Tools"
```

**Windows:**
```bash
# Install Microsoft C++ Build Tools
# Download from: https://visualstudio.microsoft.com/visual-cpp-build-tools/
```

**Rust Compiler (all platforms):**
```bash
curl --proto '=https' --tlsv1.2 -sSf https://sh.rustup.rs | sh
```

On Windows, you can also download the Rust installer from [rustup.rs](https://rustup.rs/).

### Docker (Optional)

For the Docker Compose deployment:

**macOS:**
```bash
brew install --cask docker
# Or download Docker Desktop from https://www.docker.com/
```

**Linux:**
```bash
# Ubuntu/Debian
sudo apt-get install docker.io docker-compose

# Fedora/RHEL
sudo dnf install docker docker-compose
```

**Windows:**
Download and install Docker Desktop from [docker.com](https://www.docker.com/products/docker-desktop/).

## Troubleshooting

### Installation Issues

**Problem:** pip install fails with compilation errors

```bash
# Ensure compilers are installed
# macOS
sudo xcode-select --install

# Install Rust
curl --proto '=https' --tlsv1.2 -sSf https://sh.rustup.rs | sh
```

**Problem:** Audio library errors (portaudio, libsndfile)

```bash
# macOS
brew install portaudio libsndfile ffmpeg
export DYLD_LIBRARY_PATH="/opt/homebrew/lib:$DYLD_LIBRARY_PATH"

# Linux
sudo apt-get install portaudio19-dev libsndfile1 ffmpeg
```

### Runtime Issues

**Problem:** LLM not responding or slow responses

- **For Ollama**: Ensure Ollama is running: `ollama list` should show your model
- **For local models**: Check that the model file path in config is correct and the file exists
- **First run**: LLM model loading can take 1-5 minutes depending on model size and hardware
- **Slow responses**: Large models (>7B parameters) may be slow on CPU. Consider:
  - Using a smaller quantized model (Q2_K or Q4_K variants)
  - Running with GPU acceleration if available
  - Using Ollama with GPU support

**Problem:** LLM model not found

```bash
# For Ollama models
ollama list                    # Check available models
ollama pull llama3.2          # Download if missing

# For local .gguf files
ls -la py-app/models/         # Verify file exists
# Check file path in py-app/config/default.config matches
```

**Problem:** Out of memory errors

- Reduce `max_history` in `[cltl.llm]` config (try 5-10 instead of 15)
- Use a smaller model (e.g., Llama 3.2 1B instead of 8B)
- Use more aggressive quantization (Q2_K instead of Q4_K or Q8)

**Problem:** ASR models downloading slowly

First run downloads Whisper models (~150MB for base model) from Hugging Face. This can take 2-10 minutes depending on your connection. Models are cached in `~/.cache/huggingface/` for subsequent runs.

**Problem:** Chat UI not loading

- Verify application is running: `ps aux | grep app.py`
- Check port 8000 is available: `lsof -i :8000`
- Try: [http://127.0.0.1:8000/chatui/static/chat.html](http://127.0.0.1:8000/chatui/static/chat.html)

**Problem:** Docker container won't start

```bash
# Check logs
docker-compose logs

# Check RabbitMQ health
docker-compose ps

# Restart services
docker-compose restart
```

### Getting Help

1. Check logs in `py-app/storage/event_log/`
2. Enable debug logging in `config/logging.config`
3. Review [cltl-combot documentation](https://github.com/leolani/cltl-combot)
4. Check component-specific READMEs in their repositories
5. Open an issue on the relevant GitHub repository

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

Distributed under the MIT License. See [LICENSE](https://github.com/leolani/cltl-combot/blob/main/LICENCE) for more information.

## Authors

- [Taewoon Kim](https://tae898.github.io/)
- [Thomas Baier](https://www.linkedin.com/in/thomas-baier-05519030/)
- [Selene Báez Santamaría](https://selbaez.github.io/)
- [Piek Vossen](https://github.com/piekvossen)

## References

For more information about the CLTL framework and related projects:

- [CLTL Combot Framework](https://github.com/leolani/cltl-combot)
- [CLTL LLM Module](https://github.com/leolani/cltl-llm)
- [EMISSOR Framework](https://github.com/leolani/emissor)
- [Leolani Platform](https://github.com/leolani)

### Academic Publications

If you use the LLM App or EMISSOR framework in your research, please cite:

```bibtex
@inproceedings{emissor:2021,
    title = {EMISSOR: A platform for capturing multimodal interactions as Episodic Memories and Interpretations with Situated Scenario-based Ontological References},
    author = {Selene Baez Santamaria and Thomas Baier and Taewoon Kim and Lea Krause and Jaap Kruijt and Piek Vossen},
    url = {https://mmsr-workshop.github.io/programme},
    booktitle = {Proceedings of the MMSR workshop "Beyond Language: Multimodal Semantic Representations", IWSC2021},
    year = {2021}
}
```

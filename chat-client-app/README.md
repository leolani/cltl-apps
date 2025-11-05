# Chat Client App

A lightweight chat UI client for the CLTL (Computational Lexicology & Terminology Lab) framework. This application provides a text-based chat interface that connects to existing CLTL services via a distributed event bus, allowing users to interact with conversational AI systems through a web interface.

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

The Chat Client App is a minimal, text-only conversational interface designed to connect to existing CLTL-based services. Unlike full CLTL applications that include speech recognition, language models, and other processing components, this app focuses solely on providing a chat UI that communicates with external services through a distributed event bus (RabbitMQ).

**Key features:**
- **Lightweight chat interface**: Web-based chat UI for text interaction
- **Event bus integration**: Connects to external CLTL services via RabbitMQ
- **Context management**: Tracks conversation scenarios and speaker context
- **Data persistence**: Stores conversation history using the EMISSOR framework
- **Microservice architecture**: Designed as a thin client in distributed CLTL deployments
- **Minimal dependencies**: ~50 packages vs. full CLTL apps with 90+ packages

**What's NOT included:**
- No speech recognition (ASR)
- No voice input/output
- No language model or conversational AI logic
- No audio/video processing
- No backend server for microphone/camera

This app is designed to be a **pure chat client** that sends text input to external services and displays their responses.

## Getting Started

### Prerequisites

#### Required: External RabbitMQ Server

The Chat Client App requires a RabbitMQ message broker to communicate with other CLTL services. You have two options:

**Option 1: Use RabbitMQ from an existing CLTL service**

If you're connecting to an existing CLTL application (like llm-app or eliza-app) that already runs RabbitMQ, simply configure the chat client to connect to that instance.

**Option 2: Run RabbitMQ with docker-compose (for testing)**

For testing purposes, you can use the included RabbitMQ service in the docker-compose setup:

```bash
cd docker-app
docker-compose --profile rabbitmq up
```

This will start both the chat client and a RabbitMQ instance. The RabbitMQ Management UI will be available at [http://localhost:15672](http://localhost:15672) (Username: `cltl`, Password: `cltl123`).

**Note:** This option is primarily for testing. In production scenarios, you typically connect to an existing RabbitMQ instance from another CLTL service or a shared message broker.

#### System Requirements

- **Python**: 3.8 to 3.10 (for local Python deployment)
- **Docker**: For containerized deployment
- **RabbitMQ**: External message broker (running separately or as part of another CLTL service)

### Installation

#### Option 1: Docker Compose (Recommended)

**Prerequisites**: Docker and Docker Compose installed

1. **Configure RabbitMQ connection**

   Edit `docker-app/config/default.config` to point to your RabbitMQ server:

   ```ini
   [cltl.event.kombu]
   server: amqp://cltl:cltl123@<rabbitmq-host>:5672/
   exchange: cltl.combot
   type: direct
   compression: bzip2
   ```

   Replace `<rabbitmq-host>` with:
   - `host.docker.internal` - if RabbitMQ is running on your host machine
   - `rabbitmq` - if using the optional RabbitMQ profile
   - `<ip-address>` - if RabbitMQ is running on another machine

2. **Build and run**

   ```bash
   cd docker-app
   docker-compose up --build
   ```

   **For testing with bundled RabbitMQ**:
   ```bash
   docker-compose --profile rabbitmq up --build
   ```

#### Option 2: Local Python Application

**Prerequisites**: Python 3.8-3.10

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

   **Note:** First installation may take 5-10 minutes to download and install all CLTL components.

3. **Configure RabbitMQ connection**

   Edit `py-app/config/default.config` to point to your RabbitMQ server (see Docker step 1 above).

### Running the Application

#### Docker Deployment

```bash
cd docker-app
docker-compose up
```

The application will start and connect to the configured RabbitMQ server.

**Access points:**
- **Chat UI**: [http://localhost:8000/chatui/static/chat.html](http://localhost:8000/chatui/static/chat.html)
- **EMISSOR Data API**: [http://localhost:8000/emissor](http://localhost:8000/emissor)

**Management commands:**
```bash
docker-compose down              # Stop services
docker-compose logs -f           # View logs
docker-compose ps                # Check status
```

#### Local Python Deployment

```bash
cd py-app
source venv/bin/activate     # macOS/Linux
# OR
venv\Scripts\activate        # Windows

python app.py
```

Once started, the application will:
1. Connect to RabbitMQ
2. Start a conversation scenario
3. Wait for user input through the Chat UI

**Access points:**
- **Chat UI**: [http://localhost:8000/chatui/static/chat.html](http://localhost:8000/chatui/static/chat.html)
- **EMISSOR Data API**: [http://localhost:8000/emissor](http://localhost:8000/emissor)

Press `Ctrl+C` to stop the application.

## Application Architecture

The Chat Client App is a minimal CLTL application focused on chat UI functionality and event bus integration.

### Core Components

#### Chat UI (`cltl-chat-ui`)

Web-based chat interface for text interaction.

**Responsibilities:**
- Display conversation history
- Accept user text input
- Show responses from external services
- Publish user messages to the event bus
- Subscribe to response messages from the event bus

#### Context Service (`app-service/context`)

Manages conversation context and state.

**Responsibilities:**
- Create and manage conversation scenarios
- Track speaker identity
- Publish scenario lifecycle events (start/stop)
- Maintain conversation metadata

#### EMISSOR Data Storage (`cltl-emissor-data`)

Stores conversation data using the EMISSOR framework.

**Responsibilities:**
- Persist text signals (user input and responses)
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

The Chat Client App communicates with external services through RabbitMQ using a publish-subscribe pattern.

#### Key Event Topics

| Topic | Chat Client Role | Purpose |
|-------|-----------------|---------|
| `cltl.topic.text_in` | **Publisher** | User messages typed in Chat UI |
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
          │ (user messages)           │ (responses)
          ▼                           │
┌─────────────────────────────────────▼───────────────────┐
│              Chat Client App (This App)                  │
│  ┌──────────────────────────────────────────────────┐   │
│  │  Chat UI (http://localhost:8000/chatui)          │   │
│  │  - User types message                             │   │
│  │  - Displays response                              │   │
│  └──────────────────────────────────────────────────┘   │
│  ┌──────────────────────────────────────────────────┐   │
│  │  Context Service                                  │   │
│  │  - Manages scenarios                              │   │
│  │  - Tracks conversation state                      │   │
│  └──────────────────────────────────────────────────┘   │
│  ┌──────────────────────────────────────────────────┐   │
│  │  EMISSOR Data Storage                             │   │
│  │  - Archives conversation                          │   │
│  └──────────────────────────────────────────────────┘   │
└──────────────────────────────────────────────────────────┘

┌─────────────────────────────────────────────────────────┐
│           External CLTL Service (Separate App)           │
│  - Subscribes to cltl.topic.text_in                     │
│  - Processes messages (LLM, ELIZA, custom logic, etc.)  │
│  - Publishes responses to cltl.topic.text_out          │
└─────────────────────────────────────────────────────────┘
```

### Conversation Flow

1. **User types message in Chat UI**
2. **Chat Client App publishes to `cltl.topic.text_in`** (via RabbitMQ)
3. **External service receives message** (listens on `cltl.topic.text_in`)
4. **External service processes message** (using LLM, ELIZA, or custom logic)
5. **External service publishes response to `cltl.topic.text_out`** (via RabbitMQ)
6. **Chat Client App receives response** (subscribes to `cltl.topic.text_out`)
7. **Chat UI displays response to user**
8. **EMISSOR Data Storage archives entire conversation**

The Chat Client App is agnostic to how messages are processed - it only handles input/output through the event bus.

## Configuration Guide

Configuration is managed through INI-style files in `py-app/config/` (or `docker-app/config/` for Docker).

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

- **RabbitMQ on host machine** (from Docker):
  ```ini
  server: amqp://cltl:cltl123@host.docker.internal:5672/
  ```

- **RabbitMQ in separate container**:
  ```ini
  server: amqp://cltl:cltl123@rabbitmq:5672/
  ```

- **RabbitMQ on remote server**:
  ```ini
  server: amqp://cltl:cltl123@192.168.1.100:5672/
  ```

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
topics: cltl.topic.scenario,
        cltl.topic.text_in, cltl.topic.text_out,
        cltl.desire, cltl.intention
```

#### BDI Configuration

```ini
[cltl.bdi]
topic_intention: cltl.topic.intention
topic_desire: cltl.topic.desire
model: {"init": {"chat": "init"}, "chat": {"quit": "!quit"}, "quit": {}}
```

This defines the conversation state machine:
- `init` → `chat` (on "init" intention)
- `chat` → `quit` (on "!quit" keyword)

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
├── text.json                # Text signal metadata and annotations
└── text/                    # Text files (.csv)
```

**Note:** The Chat Client App only stores text signals. Audio, video, and image signals are not captured since this app has no speech or vision capabilities.

#### Storage and Access

The EMISSOR Data Service provides a REST API at: [http://localhost:8000/emissor](http://localhost:8000/emissor)

**Key Endpoints:**
- `GET /scenarios` - List all scenarios
- `GET /scenarios/{id}` - Get scenario metadata
- `GET /scenarios/{id}/signals/text` - Get text signals for a scenario

For more details on the EMISSOR data format, see the [EMISSOR documentation](https://github.com/leolani/emissor).

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
- For Docker, use `host.docker.internal` instead of `localhost` to reach host machine

**Problem:** Chat UI loads but no responses appear

**Possible causes:**
1. No external service is listening on `cltl.topic.text_in`
2. External service is not publishing to `cltl.topic.text_out`
3. RabbitMQ exchange/topic mismatch

**Solution:**
- Check RabbitMQ Management UI to verify messages are being published
- Ensure external service is connected to same RabbitMQ instance
- Verify topic names match between chat client and external service
- Check logs for both services: `docker-compose logs -f`

**Problem:** Chat UI not loading

- Verify application is running: `ps aux | grep app.py` or `docker-compose ps`
- Check port 8000 is available: `lsof -i :8000`
- Try: [http://127.0.0.1:8000/chatui/static/chat.html](http://127.0.0.1:8000/chatui/static/chat.html)

**Problem:** Docker container won't start

```bash
# Check logs
docker-compose logs

# Rebuild from scratch
docker-compose down
docker-compose build --no-cache
docker-compose up
```

### Getting Help

1. Check logs in `py-app/storage/event_log/`
2. Enable debug logging in `config/logging.config`
3. Review [cltl-combot documentation](https://github.com/leolani/cltl-combot)
4. Check RabbitMQ Management UI for message flow
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

Distributed under the MIT License. See [LICENSE](py-app/LICENSE) for more information.

## Authors

- [Taewoon Kim](https://tae898.github.io/)
- [Thomas Baier](https://www.linkedin.com/in/thomas-baier-05519030/)
- [Selene Báez Santamaría](https://selbaez.github.io/)
- [Piek Vossen](https://github.com/piekvossen)

## References

For more information about the CLTL framework and related projects:

- [CLTL Combot Framework](https://github.com/leolani/cltl-combot)
- [EMISSOR Framework](https://github.com/leolani/emissor)
- [Leolani Platform](https://github.com/leolani)

### Academic Publications

If you use the Chat Client App or EMISSOR framework in your research, please cite:

```bibtex
@inproceedings{emissor:2021,
    title = {EMISSOR: A platform for capturing multimodal interactions as Episodic Memories and Interpretations with Situated Scenario-based Ontological References},
    author = {Selene Baez Santamaria and Thomas Baier and Taewoon Kim and Lea Krause and Jaap Kruijt and Piek Vossen},
    url = {https://mmsr-workshop.github.io/programme},
    booktitle = {Proceedings of the MMSR workshop "Beyond Language: Multimodal Semantic Representations", IWSC2021},
    year = {2021}
}
```

# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

This is the LLM App repository - a conversational AI application built using the CLTL (Computational Lexicology & Terminology Lab) framework, powered by Large Language Models (LLMs). The project uses a simplified structure where CLTL components are installed directly from GitHub repositories via pip, making it easy to set up and deploy.

## Architecture

The LLM App follows a modular, event-driven architecture with the following key components:

### Core Components
- **Backend Server** (`cltl-backend`): Provides REST API for raw audio/video signals and manages device access
- **Voice Activity Detection** (`cltl-vad`): Detects speech activity in audio streams using WebRTC VAD
- **Automatic Speech Recognition** (`cltl-asr`): Transcribes audio to text (supports Whisper, Google ASR, Wav2Vec, SpeechBrain)
- **LLM Module** (`cltl-llm`): Core conversational AI logic powered by Large Language Models (Llama, Qwen, and other compatible models)
- **Chat UI** (`cltl-chat-ui`): Web-based chat interface for text interaction
- **Context Service** (`app-service/context`): Manages conversation context and state
- **EMISSOR Data Storage** (`cltl-emissor-data`): Handles structured data storage using the EMISSOR framework

### Event System
Components communicate through an event bus using the EMISSOR framework for structured data exchange. Events include audio signals, text signals, voice activity, and conversation state changes.

Two event bus implementations are available:
- **SynchronousEventBus**: In-memory, synchronous communication within a single Python process (used in py-app)
- **Kombu EventBus with RabbitMQ**: Distributed, asynchronous communication through a message broker (used in docker-app)

## Development Commands

### Initial Setup
```bash
# Clone the repository
git clone https://github.com/leolani/eliza-app.git
cd eliza-app
```

### Local Python Application Setup
```bash
cd py-app

# Create and activate virtual environment
python -m venv venv
source venv/bin/activate  # macOS/Linux

# Install dependencies from requirements.txt
pip install --upgrade pip
pip install -r requirements.txt
```

### Run the Application

#### Option 1: Local Python Application (with SynchronousEventBus)
```bash
cd py-app
source venv/bin/activate
python app.py
```

#### Option 2: Docker Compose (with RabbitMQ/Kombu EventBus)
```bash
cd docker-app
docker-compose up --build
```

## Project Structure

- **py-app/**: Local Python application directory
  - `app.py`: Main application entry point
  - `requirements.txt`: Dependencies pointing to GitHub repositories
  - `venv/`: Virtual environment (created during setup)
  - `config/`: Configuration files (default.config, logging.config)
  - `storage/`: Local storage for audio, images, and EMISSOR data
  - `src/`: Application-specific source code
- **docker-app/**: Docker Compose deployment
  - `docker-compose.yml`: Service orchestration with RabbitMQ
  - `Dockerfile`: Container build instructions

## Configuration

### Main Config
- **Location**: `py-app/config/default.config`
- **Format**: INI-style configuration sections for each component
- **Key Settings**:
  - Audio: 16kHz sampling, single channel
  - ASR: Whisper implementation by default
  - Backend: Local server on port 8000
  - VAD: WebRTC with configurable thresholds

### Runtime Deployment Options
1. **Local Python Application**: All components in single process with in-memory SynchronousEventBus (recommended for development)
2. **Docker Compose**: Containerized application with RabbitMQ message broker using Kombu EventBus (recommended for production)

## Application Runtime

After starting with `python app.py`:
- Backend server runs on `http://localhost:8000`
- Chat UI available at `http://localhost:8000/chatui/static/chat.html`
- EMISSOR data API at `http://localhost:8000/emissor`
- Storage service at `http://localhost:8000/storage`

The application supports both voice input (with ASR) and text input through the web UI.

## Dependency Management

The project uses a simplified dependency management approach:
- Dependencies are specified in `py-app/requirements.txt`
- CLTL components point directly to GitHub repositories with specific commit hashes
- No git submodules are used
- Installation is a simple `pip install -r requirements.txt`

Example from requirements.txt:
```
cltl.backend[host,service,impl] @ git+https://github.com/leolani/cltl-backend@e604a929...
cltl.asr[impl,service,whisper] @ git+https://github.com/leolani/cltl-asr@99df4e7a...
```

### For Active Component Development
If you need to work on a specific CLTL component:
1. Clone the component repository separately
2. Install it in editable mode: `pip install -e /path/to/component`
3. Make changes and test immediately without reinstalling

## Development Workflow

Follow the development practices outlined in the [cltl-combot](https://github.com/leolani/cltl-combot) project for:
- Component development patterns
- Event handling conventions
- Configuration management
- Testing approaches

## Key Implementation Details

- **Dependency Injection**: Uses container pattern for service management
- **Resource Management**: Threaded resource containers for concurrent operations
- **Event Bus**: Synchronous event bus for component communication
- **Storage**: Cached audio/image storage with configurable backends
- **Modular ASR**: Pluggable ASR implementations via configuration


## Coding conventions

Write code on a level of a senior software engineer and data science/machine learning expert with senior Python knowledge.
Follow clean code standards in the spirit of *Clean Code* by Robert C. Martin.  

### Naming and Readability
- Use **clear, descriptive names** for variables, functions, classes, and modules.
- Avoid abbreviations unless they are universally recognized.
- Code should **read like prose** — assume the reader is smart but not omniscient.

### Function Design
- Functions should be:
  - **Small** (ideally 5–15 lines)
  - **Do one thing only** (Single Responsibility Principle), i.e. all code used in a function should be on the samelevel of abstraction
  - Named clearly based on what they do
- Prefer **top-down readability**: high-level functions should summarize the intent clearly.
- Avoid excessive branching — use early returns to reduce nesting.

### Code Structure
- Keep classes and modules **cohesive** and **focused**.
- Apply **Separation of Concerns**.
- Favor **composition over inheritance** when applicable.

### Duplication and Reuse
- Avoid code duplication — **DRY** (*Don’t Repeat Yourself*).
- Extract reusable logic into helper functions, constants, or abstractions.

### Testing
- Encourage **unit tests** for critical logic.
- Promote **Test-Driven Development (TDD)** where applicable.
- Follow the AAA pattern (Arrange, Act, Assert).
- Use fixtures and mocks to isolate tests.
- Tests should be:
  - **Fast**
  - **Independent**
  - **Clear and meaningful**

### Comments and Documentation
- Only write comments when the code **cannot be made self-explanatory**. I.e. comments should explain why the code is
  doing something, not what it is doing, and should be only added if it is necessary to explain this, which should be
  the exception.
- Use **docstrings** for public functions and classes.
- Prefer code that explains itself — use comments to explain **why**, not **what**.

### Error Handling
- Handle errors **gracefully** and explicitly.
- Use **early returns** to reduce nesting and improve clarity.
- Use **exceptions** for exceptional cases — not for normal control flow.

### General Style
- Favor **immutability** and **pure functions** where practical.
- Minimize side effects.
- Ensure code is **consistent** with the surrounding style and conventions.

### Output Expectations (for AI code generation)
When generating or reviewing code, always include:

- **Clean, idiomatic code** in the target language  
- **Brief explanation or reasoning** (if helpful)  
- **Example usage or test case** (when appropriate)  
- **Improvement suggestions** (if reviewing existing code)  

### Python specific

#### Naming and Readability
- Use `snake_case` for functions and variables, `PascalCase` for classes, and `UPPER_CASE` for constants.
- Avoid single-letter names except for throwaway variables (e.g. `for _ in range(n)`).

#### Function Design
- Use default arguments and keyword arguments for clarity and flexibility.
- Prefer keyword-only arguments in functions with many parameters (using `*`).
- Use type hints for paremeters where they are helpful

#### Code Structure
- Use modules and packages to separate concerns and keep code modular.
- Follow PEP 8 for code layout (e.g., spacing, line length, imports order).
- Structure scripts with:
  ```python
  if __name__ == "__main__":
      main()
  ```
  
#### Imports
- Don't use wildcard imports
- Prefer empty `__init__.py` files
- Never manipulate the Python Path from code, e.g. with `sys.path.append` or similar, use importlib instead

#### Duplication and Reuse
- Use context managers (`with` statement) for managing resources like files or DB connections.
- Prefer built-in functions and standard libraries over custom reimplementations.

#### Testing
- Write unit tests using `pytest`.

#### Comments and Documentation
- Use docstrings (`""" """`) for all public modules, classes, and functions.
- Follow PEP 257 for docstring conventions.

#### Error Handling
- Use try/except blocks sparingly and specifically:
- Avoid catching general `Exception` unless absolutely necessary.
- Use custom exception classes for clarity in larger applications.

#### Pythonic Practices
- Prefer list/dict comprehensions over loops when readable:
  ```python
  squares = [x**2 for x in range(10)]
  ```
- Use `enumerate()` and `zip()` instead of manual index tracking.
- Leverage unpacking:
  ```python
  a, b = b, a  # swap
  ```
- Prefer `is` for `None`, not `==`.
- Write truthy/falsey expressions idiomatically:
  ```python
  if not items:  # instead of len(items) == 0
  ```

### Final Note
You are my **code quality compass**. Help me write code I’ll be proud of in six months.





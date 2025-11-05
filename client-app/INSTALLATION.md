# Audio Processing Application - Installation Guide

This comprehensive guide provides step-by-step instructions for installing an audio-only conversational AI application with backend, ASR (Automatic Speech Recognition), VAD (Voice Activity Detection), and data storage components on Windows, Linux, and macOS.

## Table of Contents

- [Overview](#overview)
- [System Requirements](#system-requirements)
- [Prerequisites by Operating System](#prerequisites-by-operating-system)
  - [macOS](#macos)
  - [Linux (Ubuntu/Debian)](#linux-ubuntudebian)
  - [Windows](#windows)
- [Python Installation](#python-installation)
- [System Libraries for Audio Support](#system-libraries-for-audio-support)
- [Installing the Application](#installing-the-application)
- [Running the Application](#running-the-application)
- [Troubleshooting](#troubleshooting)
- [Module-Specific Requirements](#module-specific-requirements)

## Overview

This application is built on the CLTL framework and consists of four core Python modules:
- **cltl-backend**: Audio signal processing and REST API
- **cltl-asr**: Automatic Speech Recognition (transcription)
- **cltl-vad**: Voice Activity Detection
- **cltl-emissor-data**: Data storage and management

All modules are provided as pre-built Python packages and can be installed directly using pip, without requiring the make build system.

## System Requirements

### Minimum Requirements
- **Python**: 3.9 - 3.10 (required for cltl-asr)
- **RAM**: 4GB minimum, 8GB recommended (for ASR models)
- **Disk Space**: 3GB for dependencies and ASR models
- **Operating System**:
  - macOS 10.15 or later
  - Ubuntu 20.04 or later / Debian 10 or later
  - Windows 10 or later

### Build Tools (Optional)
- C compiler (GCC, Clang, or MSVC) - only if pre-built wheels are unavailable
- Rust compiler (optional, for some Python dependencies)

**Note**: Most packages now provide pre-built wheels for common platforms. Try installation first; only install build tools if you encounter compilation errors.

## Prerequisites by Operating System

### macOS

#### 1. Install Homebrew
If not already installed, install Homebrew (recommended package manager for macOS):

```bash
/bin/bash -c "$(curl -fsSL https://raw.githubusercontent.com/Homebrew/install/HEAD/install.sh)"
```

#### 2. Install Command Line Tools (Optional but Recommended)
Install Xcode Command Line Tools for C/C++ compilation:

```bash
sudo xcode-select --install
```

**Why you might need this:**
- PyAudio compilation (if pre-built wheel not available for your Python/macOS version)
- Some dependencies may need to compile C extensions

**Why you might NOT need this:**
- Most packages have pre-built wheels for macOS (Intel and Apple Silicon)
- If installation works without it, you can skip this step

**If you encounter errors about invalid clang versions:**
```bash
sudo rm -rf /Library/Developer/CommandLineTools
sudo xcode-select --install
```

**Alternative**: Try installing without Command Line Tools first. If pip fails with compilation errors, then install the tools.

#### 3. Install Python
Install Python 3.10 using Homebrew:

```bash
brew install python@3.10
```

Add Python to your PATH (add to `~/.zshrc`):

```bash
export PATH="$(brew --prefix)/opt/python@3.10/libexec/bin:$PATH"
```

Verify installation:

```bash
python --version  # Should show Python 3.10.x
which python
```

#### 4. Install Audio System Libraries
Install PortAudio, libsndfile, and ffmpeg (all required for audio processing):

```bash
brew install portaudio libsndfile ffmpeg
```

**Important**: Homebrew may not link `libsndfile` properly. Add this to your `~/.zshrc`:

```bash
export DYLD_LIBRARY_PATH="$(brew --prefix)/lib:$DYLD_LIBRARY_PATH"
```

Then reload:

```bash
source ~/.zshrc
```

#### 5. Install Optional Dependencies
```bash
# Rust compiler (optional, for some Python packages)
brew install rust
```

### Linux (Ubuntu/Debian)

#### 1. Update System Packages
```bash
sudo apt-get update
sudo apt-get upgrade
```

#### 2. Install Build Tools
```bash
sudo apt-get install -y build-essential git curl wget make
```

#### 3. Install Python
Install Python 3.10 and development headers:

```bash
sudo apt-get install -y python3.10 python3.10-dev python3.10-venv python3-pip
```

Create symbolic links if needed:

```bash
sudo update-alternatives --install /usr/bin/python python /usr/bin/python3.10 1
sudo update-alternatives --install /usr/bin/pip pip /usr/bin/pip3 1
```

Verify installation:

```bash
python --version  # Should show Python 3.10.x
```

#### 4. Install Audio System Libraries
Install PortAudio, ALSA, and related audio libraries:

```bash
sudo apt-get install -y \
    portaudio19-dev \
    libasound2-dev \
    libsndfile1-dev \
    ffmpeg \
    pulseaudio \
    alsa-utils
```

#### 5. Install Optional Dependencies
```bash
# Rust compiler (optional, for some Python packages)
curl --proto '=https' --tlsv1.2 -sSf https://sh.rustup.rs | sh
source "$HOME/.cargo/env"
```

### Windows

#### 1. Install Python
Download and install Python 3.10 from [python.org](https://www.python.org/downloads/):
- Make sure to check "Add Python to PATH" during installation
- Verify installation by opening Command Prompt:

```cmd
python --version
```

#### 2. Install Visual Studio Build Tools
Download and install [Visual Studio Build Tools](https://visualstudio.microsoft.com/downloads/):
- Select "Desktop development with C++" workload
- This provides the MSVC compiler needed for some Python packages

#### 3. Install Git
Download and install [Git for Windows](https://git-scm.com/download/win)

#### 4. Install Audio System Libraries

**PortAudio:**
Download pre-built PortAudio binaries:
1. Visit [PortAudio downloads](http://www.portaudio.com/download.html)
2. Download the Windows build
3. Extract to `C:\portaudio`
4. Add to system PATH: `C:\portaudio\bin`

**Alternative: Use conda (recommended for Windows)**
```cmd
# Install Miniconda
# Download from https://docs.conda.io/en/latest/miniconda.html

# Create environment
conda create -n eliza python=3.10
conda activate eliza

# Install portaudio via conda
conda install portaudio
```

#### 5. Install FFmpeg
Download FFmpeg from [ffmpeg.org](https://ffmpeg.org/download.html):
1. Extract to `C:\ffmpeg`
2. Add `C:\ffmpeg\bin` to system PATH

#### 6. Install Optional Dependencies
```cmd
# Rust compiler (optional, for some Python packages)
# Download and run rustup-init.exe from https://rustup.rs/
# Follow the prompts
```

## Python Installation

### Important Notes on Python Version

**Required Python Version: 3.9 - 3.10**

- `cltl-asr` requires Python >= 3.9
- Most other modules require Python >= 3.7-3.8
- **Recommended: Python 3.10** for best compatibility

### Avoiding Anaconda

**Important**: We recommend NOT using Anaconda for this project because:
1. Anaconda's pip integration can cause dependency conflicts
2. Anaconda and pyenv don't work well together
3. Some packages may not install correctly via conda

If you must use conda, create a clean environment:

```bash
conda create -n eliza python=3.10
conda activate eliza
# Then follow the build instructions
```

### Using pyenv (Recommended for macOS/Linux)

```bash
# Install pyenv
curl https://pyenv.run | bash

# Add to ~/.bashrc or ~/.zshrc
export PATH="$HOME/.pyenv/bin:$PATH"
eval "$(pyenv init -)"
eval "$(pyenv virtualenv-init -)"

# Install Python 3.10
pyenv install 3.10.13
pyenv global 3.10.13
```

## System Libraries for Audio Support

### Audio Processing Dependencies

The following Python packages require system libraries to be installed:

#### PyAudio
- **Purpose**: Audio I/O, microphone input
- **System Library**: PortAudio
- **Used by**: cltl-backend

#### soundfile
- **Purpose**: Audio file reading/writing
- **System Library**: libsndfile
- **Used by**: cltl-vad, cltl-asr, cltl-backend

#### sounddevice
- **Purpose**: Audio playback and recording
- **System Library**: PortAudio
- **Used by**: cltl-backend

#### webrtcvad
- **Purpose**: Voice Activity Detection
- **System Library**: None (includes C extension)
- **Used by**: cltl-vad

## Installing the Application

### 1. Create a Python Virtual Environment

It's strongly recommended to use a virtual environment to avoid conflicts with system packages.

**macOS/Linux:**
```bash
# Create project directory
mkdir audio-app
cd audio-app

# Create virtual environment
python -m venv venv

# Activate virtual environment
source venv/bin/activate
```

**Windows:**
```cmd
REM Create project directory
mkdir audio-app
cd audio-app

REM Create virtual environment
python -m venv venv

REM Activate virtual environment
venv\Scripts\activate
```

### 2. Create requirements.txt

Create a `requirements.txt` file with the following content:

```text
# Core dependencies
numpy
emissor

# Backend with audio support
cltl.backend[service]

# ASR with Whisper support
cltl.asr[whisper,service]

# VAD (Voice Activity Detection)
cltl.vad[impl,service]

# Data storage
cltl.emissor-data[impl,service,client]

# Additional dependencies
cltl.combot
flask<2.3
werkzeug
requests
```

**Alternative ASR options:**
- For Google ASR: Replace `cltl.asr[whisper,service]` with `cltl.asr[google,service]`
- For all implementations: Use `cltl.asr[impl,whisper,service]`
- For WhisperAPI: Use `cltl.asr[whisperapi,service]`

### 3. Install Python Packages

```bash
pip install --upgrade pip
pip install -r requirements.txt
```

**Expected Duration**: 5-15 minutes depending on your system and internet connection

**Note**: During installation, you may see compilation messages for C extensions (PyAudio, webrtcvad, etc.). This is normal.

## Running the Application

### 1. Create Your Application

Create a Python script (e.g., `app.py`) that initializes and runs the services. Example:

```python
from cltl.backend.api.backend import Backend
from cltl.backend.server import BackendServer
from cltl_service.backend.backend import BackendService
from cltl_service.asr.service import AsrService
from cltl_service.vad.service import VadService
from cltl_service.emissor_data.service import EmissorDataService

# Initialize services based on your configuration
# See module documentation for specific setup

if __name__ == "__main__":
    # Start your application
    pass
```

### 2. Access the Services

Once running, the backend typically provides:

- **Backend API**: http://localhost:8000 (configurable)
- **EMISSOR Data API**: http://localhost:8000/emissor (if enabled)
- **Storage Service**: http://localhost:8000/storage (if enabled)

**Note**: Specific endpoints and ports depend on your application configuration.

## Troubleshooting

### Common Issues

#### 1. Python Version Issues

**Error**: "Python version not supported" or "Requires Python >=3.9"

**Solution**: Ensure you're using Python 3.9-3.10:
```bash
python --version
```

If wrong version, install Python 3.10 as described in the [Python Installation](#python-installation) section.

#### 2. PortAudio Not Found

**Error**: "Cannot find PortAudio" or "portaudio.h: No such file or directory"

**macOS:**
```bash
brew install portaudio
export DYLD_LIBRARY_PATH="$(brew --prefix)/lib:$DYLD_LIBRARY_PATH"
```

**Linux:**
```bash
sudo apt-get install portaudio19-dev
```

**Windows:**
Use conda to install portaudio:
```cmd
conda install portaudio
```

Or download pre-built PyAudio wheel:
```cmd
pip install pipwin
pipwin install pyaudio
```

#### 3. libsndfile Issues on macOS

**Error**: "Library not loaded: libsndfile.dylib"

**Solution**:
```bash
brew install libsndfile
export DYLD_LIBRARY_PATH="$(brew --prefix)/lib:$DYLD_LIBRARY_PATH"
# Add to ~/.zshrc to make permanent:
echo 'export DYLD_LIBRARY_PATH="$(brew --prefix)/lib:$DYLD_LIBRARY_PATH"' >> ~/.zshrc
```

#### 4. PyAudio Installation Fails

**Error**: Compilation errors during `pip install` related to PyAudio

**macOS:**
```bash
brew install portaudio
pip install pyaudio
```

**Linux:**
```bash
sudo apt-get install portaudio19-dev python3-dev
pip install pyaudio
```

**Windows:**
```cmd
# Recommended: Use pre-built wheel
pip install pipwin
pipwin install pyaudio

# Alternative: Use conda
conda install pyaudio
```

#### 5. soundfile Import Errors

**Error**: "soundfile could not find the libsndfile library"

**macOS:**
```bash
brew install libsndfile
export DYLD_LIBRARY_PATH="$(brew --prefix)/lib:$DYLD_LIBRARY_PATH"
```

**Linux:**
```bash
sudo apt-get install libsndfile1-dev
```

**Windows:**
Usually works without additional setup. If issues persist, reinstall:
```cmd
pip uninstall soundfile
pip install soundfile
```

#### 6. Permission Denied on Audio Devices (Linux)

**Error**: "PermissionError: [Errno 13] Permission denied: '/dev/snd/...' "

**Solution**: Add user to audio group:
```bash
sudo usermod -a -G audio $USER
# Log out and log back in for changes to take effect
```

#### 7. Rust Compiler Errors

**Error**: "cargo not found" or "error: linker `cc` not found"

**Solution**:
```bash
# Install Rust
curl --proto '=https' --tlsv1.2 -sSf https://sh.rustup.rs | sh
source $HOME/.cargo/env

# On Linux, also ensure build tools are installed
sudo apt-get install build-essential
```

#### 8. Package Not Found Errors

**Error**: "No matching distribution found for cltl.backend"

**Solution**: Ensure you have specified the correct package names and extras:
```bash
# Make sure to use brackets for extras
pip install "cltl.backend[service]"
pip install "cltl.asr[whisper,service]"
```

#### 9. Conflicting Dependencies

**Error**: "ERROR: pip's dependency resolver does not currently take into account all the packages..."

**Solution**: Try installing in a clean virtual environment:
```bash
# Deactivate current environment
deactivate

# Remove old environment
rm -rf venv

# Create fresh environment
python -m venv venv
source venv/bin/activate  # or venv\Scripts\activate on Windows

# Install with updated pip
pip install --upgrade pip
pip install -r requirements.txt
```

## Module-Specific Requirements

This section provides detailed dependency information for each of the four core modules.

### cltl-backend

**Purpose**: Provides REST API for audio signals and manages device access

**Core Dependencies:**
- numpy

**System Libraries Needed:**
- PortAudio (for PyAudio)
- libsndfile (for soundfile)

**Recommended Installation:**
```bash
pip install "cltl.backend[service]"
```

**Includes:**
- cltl.combot
- emissor
- flask < 2.3
- pyaudio
- sounddevice
- soundfile
- requests

**Python Version**: >= 3.7

**Platform Notes:**
- macOS: Works with all audio backends
- Linux: May require audio group permissions
- Windows: Best installed via conda for audio library support

### cltl-asr

**Purpose**: Automatic Speech Recognition - transcribes audio to text

**Core Dependencies:**
- numpy

**System Libraries Needed:**
- PortAudio (for sounddevice)
- libsndfile (for soundfile)

**Recommended Installation:**
```bash
# For Whisper (local):
pip install "cltl.asr[whisper,service]"

# For Google Cloud Speech:
pip install "cltl.asr[google,service]"

# For OpenAI Whisper API:
pip install "cltl.asr[whisperapi,service]"
```

**Python Version**: >= 3.9 (required)

**ASR Implementation Options:**

1. **Whisper** (openai-whisper):
   - Runs locally
   - No API key needed
   - Requires ~3GB disk space for models
   - Good accuracy

2. **Google Cloud Speech** (google):
   - Requires Google Cloud account and API key
   - Cloud-based processing
   - Excellent accuracy

3. **Whisper API** (whisperapi):
   - Requires OpenAI API key
   - Cloud-based processing
   - Based on Whisper models

4. **Whisper C++** (whispercpp):
   - Requires separate whisper.cpp server setup
   - Best performance on macOS with Apple Silicon
   - See cltl-asr documentation for setup

**Platform Notes:**
- All options work cross-platform
- Local Whisper requires significant RAM (4GB+)
- macOS Apple Silicon: Consider Whisper C++ for best performance

### cltl-vad

**Purpose**: Voice Activity Detection - detects speech in audio streams

**Core Dependencies:**
- numpy
- webrtcvad

**System Libraries Needed:**
- libsndfile (for soundfile)

**Recommended Installation:**
```bash
pip install "cltl.vad[impl,service]"
```

**Includes:**
- soundfile
- webrtcvad
- cltl.backend
- cltl.combot
- emissor
- requests

**Python Version**: >= 3.7

**Platform Notes:**
- WebRTC VAD is fully cross-platform
- No platform-specific dependencies

### cltl-emissor-data

**Purpose**: Data storage and management using EMISSOR framework

**Core Dependencies:**
- cltl.combot
- emissor

**System Libraries Needed:**
- libsndfile (for soundfile, audio-only mode)

**Recommended Installation:**
```bash
pip install "cltl.emissor-data[impl,service,client]"
```

**Includes:**
- emissor
- soundfile
- flask
- requests

**Python Version**: >= 3.8

**Platform Notes:**
- Since you're not using video/images, opencv-python dependency is not critical
- Works fully cross-platform for audio data

### emissor

**Purpose**: Core EMISSOR framework for data representation

**Core Dependencies:**
- numpy
- marshmallow and related packages
- rdflib
- simplejson
- typeguard

**Installation:**
```bash
pip install emissor
```

**Python Version**: >= 3.7

**Platform Notes:**
- Pure Python package
- No system library dependencies
- Fully cross-platform

## Cross-Platform Compatibility Summary

| Component | Windows | Linux | macOS | Notes |
|-----------|---------|-------|-------|-------|
| cltl-backend | ✓ | ✓ | ✓ | Requires PortAudio on all platforms |
| cltl-asr | ✓ | ✓ | ✓ | Python 3.9+ required |
| cltl-vad | ✓ | ✓ | ✓ | WebRTC VAD works cross-platform |
| emissor | ✓ | ✓ | ✓ | Pure Python, fully compatible |
| cltl-emissor-data | ✓ | ✓ | ✓ | Audio-only: fully compatible |
| PyAudio | ⚠ | ✓ | ✓ | Windows: use conda or pre-built wheels |
| soundfile | ✓ | ✓ | ⚠ | macOS: may need DYLD_LIBRARY_PATH |

**Legend:**
- ✓ Full support
- ⚠ Works with additional configuration

## Environment Variables

### macOS
Add these to your `~/.zshrc`:

```bash
# Python path (if using Homebrew)
export PATH="$(brew --prefix)/opt/python@3.10/libexec/bin:$PATH"

# Library path for libsndfile (REQUIRED for soundfile)
export DYLD_LIBRARY_PATH="$(brew --prefix)/lib:$DYLD_LIBRARY_PATH"
```

After editing, reload:
```bash
source ~/.zshrc
```

### Linux
Add these to your `~/.bashrc` (if using Rust):

```bash
# Rust cargo (if installed)
export PATH="$HOME/.cargo/bin:$PATH"
```

After editing, reload:
```bash
source ~/.bashrc
```

### Windows
Set system environment variables through:
1. System Properties → Advanced → Environment Variables
2. Add to PATH:
   - Python installation directory
   - `C:\ffmpeg\bin` (if using manual FFmpeg install)

Or use conda environment which handles paths automatically.

## Quick Start Summary

For experienced users, here's a quick reference:

### macOS
```bash
# Prerequisites (Xcode Command Line Tools optional - try without first)
brew install python@3.10 portaudio libsndfile ffmpeg
export DYLD_LIBRARY_PATH="$(brew --prefix)/lib:$DYLD_LIBRARY_PATH"

# Setup
python -m venv venv
source venv/bin/activate
pip install --upgrade pip
pip install "cltl.backend[service]" "cltl.asr[whisper,service]" "cltl.vad[impl,service]" "cltl.emissor-data[impl,service,client]"

# If you get compilation errors, install Command Line Tools:
# sudo xcode-select --install
```

### Linux (Ubuntu/Debian)
```bash
# Prerequisites
sudo apt-get update
sudo apt-get install -y python3.10 python3.10-venv portaudio19-dev libsndfile1-dev ffmpeg

# Setup
python3.10 -m venv venv
source venv/bin/activate
pip install --upgrade pip
pip install "cltl.backend[service]" "cltl.asr[whisper,service]" "cltl.vad[impl,service]" "cltl.emissor-data[impl,service,client]"
```

### Windows (using conda)
```cmd
REM Prerequisites: Install Miniconda from https://docs.conda.io/en/latest/miniconda.html

REM Setup
conda create -n audio-app python=3.10 portaudio
conda activate audio-app
pip install --upgrade pip
pip install "cltl.backend[service]" "cltl.asr[whisper,service]" "cltl.vad[impl,service]" "cltl.emissor-data[impl,service,client]"
```

## Additional Resources

- [CLTL Combot Framework](https://github.com/leolani/cltl-combot) - Framework documentation
- [EMISSOR Documentation](https://github.com/leolani/emissor) - Data representation
- [cltl-backend](https://github.com/leolani/cltl-backend) - Backend module
- [cltl-asr](https://github.com/leolani/cltl-asr) - ASR module
- [cltl-vad](https://github.com/leolani/cltl-vad) - VAD module
- [cltl-emissor-data](https://github.com/leolani/cltl-emissor-data) - Data storage
- [PortAudio Documentation](http://www.portaudio.com/docs.html) - Audio library docs
- [Whisper.cpp](https://github.com/ggerganov/whisper.cpp) - Alternative ASR implementation

## Getting Help

If you encounter issues not covered in this guide:

1. Review the [Troubleshooting](#troubleshooting) section above

2. Check module-specific READMEs:
   - [cltl-backend README](https://github.com/leolani/cltl-backend/blob/main/README.md)
   - [cltl-asr README](https://github.com/leolani/cltl-asr/blob/main/README.md)
   - [cltl-vad README](https://github.com/leolani/cltl-vad/blob/main/README.md)
   - [emissor README](https://github.com/leolani/emissor/blob/main/README.md)
   - [cltl-emissor-data README](https://github.com/leolani/cltl-emissor-data/blob/main/README.md)

3. File an issue on the relevant component repository at [Leolani GitHub Organization](https://github.com/leolani)

## License

Distributed under the MIT License. See `LICENSE` files in individual component repositories for more information.

## Authors

- [Piek Vossen](https://github.com/piekvossen)
- [Thomas Baier](https://www.linkedin.com/in/thomas-baier-05519030/)
- [Taewoon Kim](https://tae898.github.io/)
- [Selene Báez Santamaría](https://selbaez.github.io/)

# CLTL Apps

A collection of conversational AI applications built using the CLTL (Computational Lexicology & Terminology Lab) framework. This repository demonstrates the modular, event-driven architecture of the CLTL framework through complete application examples for building communication robots and interactive agents.

## Overview

Each application in this repository showcases how to compose sophisticated conversational agents from modular CLTL components. The apps share a common architecture with pluggable components for:

- **Speech processing**: Automatic Speech Recognition (ASR), Voice Activity Detection (VAD)
- **Conversational AI**: Dialogue management with different implementations
- **Multimodal interaction**: Text and voice-based interfaces
- **Data storage**: EMISSOR framework for structured multimodal interaction data
- **Flexible deployment**: Local Python applications or Docker Compose with distributed messaging

## Applications

### [Eliza App](eliza-app/)

A conversational AI application implementing the classic ELIZA chatbot with modern speech recognition capabilities.

**Key Features:**
- Pattern-based conversation using the `cltl-eliza` component
- Classic ELIZA-style responses with rule-based matching
- Voice and text input support
- Serves as a simple introduction to the CLTL framework

**Use Case:** Educational demonstrations, testing the framework, simple rule-based conversations

[Read the full documentation →](eliza-app/README.md)

### [LLM App](llm-app/)

A sophisticated conversational AI application powered by Large Language Models (LLMs) including Llama and Qwen.

**Key Features:**
- Natural, context-aware conversations using the `cltl-llm` component
- Support for multiple LLM backends (Ollama, local GGUF models)
- Configurable system prompts, temperature, and conversation history
- Advanced dialogue capabilities with state-of-the-art language models

**Use Case:** Advanced conversational agents, research applications, production deployments requiring natural language understanding

[Read the full documentation →](llm-app/README.md)

## Architecture

Both applications share the same modular, event-driven architecture:

```
┌─────────────────────────────────────────────────────────────┐
│                    User Interaction Layer                    │
│              (Voice Input / Web Chat Interface)              │
└─────────────────────────────────────────────────────────────┘
                            │
                            ▼
┌─────────────────────────────────────────────────────────────┐
│                      Event Bus Layer                         │
│          (In-Memory or RabbitMQ Distributed)                │
└─────────────────────────────────────────────────────────────┘
                            │
        ┌───────────────────┼───────────────────┐
        ▼                   ▼                   ▼
    ┌─────────┐      ┌──────────┐      ┌──────────────┐
    │   ASR   │      │   VAD    │      │ Conversational│
    │ (Speech)│      │  (Voice) │      │    Module     │
    └─────────┘      └──────────┘      └──────────────┘
                                              │
                                        ┌─────┴─────┐
                                        ▼           ▼
                                    ┌────────┐  ┌─────┐
                                    │ Eliza  │  │ LLM │
                                    └────────┘  └─────┘
```

**The key difference:**
- **Eliza App** uses pattern-based responses (`cltl-eliza`)
- **LLM App** uses language models for natural conversations (`cltl-llm`)

## Quick Start

Each application can be run in two ways:

### Local Python Application (Development)
```bash
cd eliza-app/py-app    # or llm-app/py-app
python -m venv venv
source venv/bin/activate
pip install -r requirements.txt
python app.py
```

### Docker Compose (Production)
```bash
cd eliza-app/docker-app    # or llm-app/docker-app
docker-compose up --build
```

See individual app READMEs for detailed setup instructions and configuration options.

## Requirements

- **Python**: 3.8 to 3.10
- **System Libraries**: portaudio, libsndfile, ffmpeg (for audio processing)
- **Docker**: (Optional) For containerized deployment
- **LLM Models**: (For llm-app only) Ollama or local GGUF model files

See individual app READMEs for complete prerequisites and installation instructions.

## Repository Structure

```
cltl-apps/
├── eliza-app/           # ELIZA-based conversational app
│   ├── py-app/          # Local Python application
│   ├── docker-app/      # Docker Compose deployment
│   └── README.md        # Detailed documentation
│
├── llm-app/             # LLM-powered conversational app
│   ├── py-app/          # Local Python application
│   ├── docker-app/      # Docker Compose deployment
│   └── README.md        # Detailed documentation
│
└── README.md            # This file
```

## Contributing

Contributions are welcome! Each application follows the coding conventions outlined in their respective `CLAUDE.md` files. When contributing:

1. Follow Clean Code principles
2. Maintain consistency with existing code style
3. Update documentation for any new features
4. Test both local and Docker deployments

## Related Projects

- [CLTL Combot Framework](https://github.com/leolani/cltl-combot) - Core framework for building conversational agents
- [CLTL LLM Module](https://github.com/leolani/cltl-llm) - LLM integration for the CLTL framework
- [EMISSOR Framework](https://github.com/leolani/emissor) - Multimodal interaction data representation
- [Leolani Platform](https://github.com/leolani) - Complete conversational robot platform

## License

Distributed under the MIT License. See individual app LICENSE files for more information.

## Authors

- [Taewoon Kim](https://tae898.github.io/)
- [Thomas Baier](https://www.linkedin.com/in/thomas-baier-05519030/)
- [Selene Báez Santamaría](https://selbaez.github.io/)
- [Piek Vossen](https://github.com/piekvossen)

## Citation

If you use these applications or the EMISSOR framework in your research, please cite:

```bibtex
@inproceedings{emissor:2021,
    title = {EMISSOR: A platform for capturing multimodal interactions as Episodic Memories and Interpretations with Situated Scenario-based Ontological References},
    author = {Selene Baez Santamaria and Thomas Baier and Taewoon Kim and Lea Krause and Jaap Kruijt and Piek Vossen},
    url = {https://mmsr-workshop.github.io/programme},
    booktitle = {Proceedings of the MMSR workshop "Beyond Language: Multimodal Semantic Representations", IWSC2021},
    year = {2021}
}
```

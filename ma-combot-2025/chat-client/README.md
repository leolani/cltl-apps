# Chat UI client

This application can be used to connect to the Combot server using a browser based chat UI.

## Get started

- Download this folder, either clone the repository

      git clone https://github.com/leolani/cltl-apps.git
      cd cltl-apps/ma-combot-2025/chat-client

  or download and extract only this folder

      wget "https://github.com/leolani/cltl-apps/archive/refs/heads/main.zip"
      unzip main.zip "cltl-apps-main/ma-combot-2025/chat-client/*"
      mv cltl-apps-main/ma-combot-2025/chat-client chat-client
      rmdir cltl-apps-main

- Add your name in the [config/custom.config](config/custom.config) file
- Run

      docker compose up
- Connect to http://localhost:8000/chatui/static/chat.html
- Now you can chat with the Combot server. There will be an inital prompt that asks if you want to have a chat,
  answer that with `yes`
- To stop the current conversation, type `Goodbye`. Unfortunately, due to a bug, currently the goodbye message from the
  server is lost
- To continue with a new conversation, reload the browser page

## Prerequisites

### Docker

To run the chat client application you need to install [Docker](https://www.docker.com/) on your system.

**macOS:**
Follow the instructions for [OS X](https://docs.docker.com/get-started/get-docker/). You can also use homebrew, note that
you need to install the **cask and not plain docker**.

```bash
brew install --cask docker
# Or download Docker Desktop from https://www.docker.com/
```

**Linux:**
On Linux you need to install _docker_ and _docker-compose_. Follow the instructions for [docker](https://docs.docker.com/engine/install/)
and [docker-compose](https://docs.docker.com/compose/install/linux/#install-using-the-repository). Here some shortcuts:

```bash
# Ubuntu/Debian
sudo apt-get install docker.io docker-compose

# Fedora/RHEL
sudo dnf install docker docker-compose
```

**Windows:**
Follow the instructions for [Windows](https://docs.docker.com/get-started/get-docker/).

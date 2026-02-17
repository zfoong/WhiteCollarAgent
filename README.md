
<div align="center">
    <img src="assets/WCA_README_banner.png" alt="CraftOS Banner" width="1280"/>
</div>
<br>
<div align="center">
    <img src="assets/white_collar_agent_icons_text.png" alt="CraftOS Logo" width="480"/>
</div>
<br>

<div align="center">
  <img src="https://img.shields.io/badge/OS-Windows-blue?logo=windows&logoColor=white" alt="Windows">
  <img src="https://img.shields.io/badge/OS-Linux-yellow?logo=linux&logoColor=black" alt="Linux">
  
  <a href="https://github.com/zfoong/CraftBot">
    <img src="https://img.shields.io/github/stars/zfoong/CraftBot?style=social" alt="GitHub Repo stars">
  </a>

  <img src="https://img.shields.io/github/license/zfoong/CraftBot" alt="License">

  <a href="https://discord.gg/ZN9YHc37HG">
    <img src="https://img.shields.io/badge/Discord-Join%20the%20community-5865F2?logo=discord&logoColor=white" alt="Discord">
  </a>
<br/>
<br/>

[![SPONSORED BY E2B FOR STARTUPS](https://img.shields.io/badge/SPONSORED%20BY-E2B%20FOR%20STARTUPS-ff8800?style=for-the-badge)](https://e2b.dev/startups)
</div>

<p align="center">
  <a href="README.ja.md"> 日本語版はこちら</a> | <a href="README.cn.md"> 中文版README </a>
</p>

## 🚀 Overview
<h3 align="center">
CraftBot is your Personal AI Assistant that lives inside your machine and works 24/7 for you. 
</h3>

It can autonomously interpret tasks, plan actions, and execute actions to achieve complex goals. <br/>	
This is an open-source project and is still in development, so we welcome any suggestions, contributions, and feedback! You are free to use, host, and monetize this project (with credit given in case of distribution and monetization).

---

## ✨ Features

- 🧠 **Single Base Agent Architecture** — Simple, extendable core that handles reasoning, planning, and execution.  
- ⚙️ **CLI/GUI mode** — Agent can switch between CLI and GUI mode according to the complexity of the task. GUI mode is still in experimental phase 🧪.
- 🧩 **Subclass & Extend** — Build your own agents by inheriting from the base class.  
- 🔍 **Task Document Interface** — Define structured tasks for the agent to perform in-context learning.  
- 🧰 **Actions Library** — Reusable tools (web search, code execution, I/O, etc.).  
- ⚡ **Lightweight & Cross-Platform** — Works seamlessly across Linux and Windows.
- 💻 **Support multiple LLM providers** — Bring your own API keys (Anthropic, OpenAI, Gemini, BytePlus, or even running your own Ollama endpoint).

> [!IMPORTANT]
> **Note for GUI mode:** The GUI mode is still in experimental phase. This means you will encounter a lot of issues when the agent decides to switch to GUI mode. We are still working on it.

## 🔜 Roadmap

- [ ] **Memory Module** — Coming next!
- [ ] **External Tool integration** — Pending
- [ ] **MCP Layer** — Pending
- [ ] **Proactive Behaviour** — Pending

---

## 🧰 Getting Started

### Prerequisites
- Python **3.9+**
- `git`, `conda`, and `pip`
- An API key for your chosen LLM provider (e.g., OpenAI or Gemini)

### Installation
```bash
git clone https://github.com/zfoong/CraftBot.git
cd CraftBot
conda env create -f environment.yml
```

---

## ⚡ Quick Start

Export your API key:
```bash
export OPENAI_API_KEY=<YOUR_KEY_HERE>
or
export GOOGLE_API_KEY=<YOUR_KEY_HERE>
```
Run:
```bash
python start.py
```

This executes the built-in **CraftBot**, that you can communicate to:
1. Talk to the agent  
2. Ask it to perform complex series of tasks  
3. Run command /help to seek help
4. Get along with the AI agent
5. Do advanced computer-use tasks with a dedicated but lightweight WebRTC Linux VM

### Terminal Arguments
| Argument | Description |
| :--- | :--- |
| `--only-cpu` | Run the agent on CPU mode |
| `--fast` | Skip unecessary update checks and launch agent faster. <br> <u><b>NOTE:</b></u> You have to run without `--fast` the first time you launch |
| `--no-omniparser` | Disable the use of microsoft omniparser to analyse UI - will greatly reduce GUI action accuracy. It is highly encouraged to use omniparser |
| `--no-conda` | Installs all packages globally instead of inside a conda environment |

**EXAMPLE**
```bash
python start.py --only-cpu --fast
```

---

## 🔐 OAuth Setup (Optional)

The agent can connect to various services using OAuth. Release builds come with embedded credentials, but you can also use your own.

### Quick Start

For release builds with embedded credentials:
```
/google login    # Connect Google Workspace
/zoom login      # Connect Zoom
/slack invite    # Connect Slack
/notion invite   # Connect Notion
/linkedin login  # Connect LinkedIn
```

### Service Details

| Service | Auth Type | Command | Requires Secret? |
|---------|-----------|---------|------------------|
| Google | PKCE | `/google login` | No (PKCE) |
| Zoom | PKCE | `/zoom login` | No (PKCE) |
| Slack | OAuth 2.0 | `/slack invite` | Yes |
| Notion | OAuth 2.0 | `/notion invite` | Yes |
| LinkedIn | OAuth 2.0 | `/linkedin login` | Yes |

### Using Your Own Credentials

If you prefer to use your own OAuth credentials, add them to your `.env` file:

#### Google (PKCE - only Client ID needed)
```bash
GOOGLE_CLIENT_ID=your-client-id.apps.googleusercontent.com
```
1. Go to [Google Cloud Console](https://console.cloud.google.com/)
2. Enable Gmail, Calendar, Drive, and People APIs
3. Create OAuth credentials as **Desktop app** type
4. Copy the Client ID (secret not required for PKCE)

#### Zoom (PKCE - only Client ID needed)
```bash
ZOOM_CLIENT_ID=your-zoom-client-id
```
1. Go to [Zoom Marketplace](https://marketplace.zoom.us/)
2. Create an OAuth app
3. Copy the Client ID

#### Slack (Requires both)
```bash
SLACK_SHARED_CLIENT_ID=your-slack-client-id
SLACK_SHARED_CLIENT_SECRET=your-slack-client-secret
```
1. Go to [Slack API](https://api.slack.com/apps)
2. Create a new app
3. Add OAuth scopes: `chat:write`, `channels:read`, `users:read`, etc.
4. Copy Client ID and Client Secret

#### Notion (Requires both)
```bash
NOTION_SHARED_CLIENT_ID=your-notion-client-id
NOTION_SHARED_CLIENT_SECRET=your-notion-client-secret
```
1. Go to [Notion Developers](https://developers.notion.com/)
2. Create a new integration (Public integration)
3. Copy OAuth Client ID and Secret

#### LinkedIn (Requires both)
```bash
LINKEDIN_CLIENT_ID=your-linkedin-client-id
LINKEDIN_CLIENT_SECRET=your-linkedin-client-secret
```
1. Go to [LinkedIn Developers](https://developer.linkedin.com/)
2. Create an app
3. Add OAuth 2.0 scopes
4. Copy Client ID and Client Secret

---
## Run with container

The repository root included a Docker configuration with Python 3.10, key system packages (including Tesseract for OCR), and all Python dependencies defined in `environment.yml`/`requirements.txt` so the agent can run consistently in isolated environments. 

Below are the setup instruction of running our agent with container.

### Build the image

From the repository root:

```bash
docker build -t craftbot .
```

### Run the container

The image is configured to launch the agent with `python -m core.main` by default. To run it interactively:

```bash
docker run --rm -it craftbot
```

If you need to supply environment variables, pass an env file (for example, based on `.env.example`):

```bash
docker run --rm -it --env-file .env craftbot
```

Mount any directories that should persist outside the container (such as data or cache folders) using `-v`, and adjust ports or additional flags as needed for your deployment. The container ships with system dependencies for OCR (`tesseract`), screen automation (`pyautogui`, `mss`, X11 utilities, and a virtual framebuffer), and common HTTP clients so the agent can work with files, network APIs, and GUI automation inside the container.

### Enabling GUI/screen automation

GUI actions (mouse/keyboard events, screenshots) require an X11 server. You can either attach to your host display or run headless with `xvfb`:

* Use the host display (requires Linux with X11):

  ```bash
  docker run --rm -it 
    -e DISPLAY=$DISPLAY \
    -v /tmp/.X11-unix:/tmp/.X11-unix \
    -v $(pwd)/data:/app/core/data \
    craftbot
  ```

  Add extra `-v` mounts for any folders the agent should read/write.

* Run headlessly with a virtual display:

  ```bash
	docker run --rm -it --env-file .env craftbot bash -lc "Xvfb :99 -screen 0 1920x1080x24 & export DISPLAY=:99 && exec python -m core.main"
  ```

By default the image uses Python 3.10 and bundles the Python dependencies from `environment.yml`/`requirements.txt`, so `python -m core.main` works out of the box.

---

## 🧠 Example: Build a Custom Agent

You can easily create your own specialized agent by extending the base agent:

```python
import asyncio
from core.agent_base import AgentBase

class MyCustomAgent(AgentBase):
    def __init__(
        self,
        *,
        data_dir: str = "core/data",
        chroma_path: str = "./chroma_db",
    ):
        super().__init__(
            data_dir=data_dir,
            chroma_path=chroma_path,
        )
        # Your implementation
        def _generate_role_info_prompt(self) -> str:
            """
            Defines this agent's role, behaviour, and purpose.
            """
            return (
                "You are MyCustomAgent — an intelligent research assistant. "
                "Your role is to find, summarize, and synthesize information from multiple sources. "
                "You respond concisely, prioritize factual accuracy, and cite sources when relevant. "
                "If you cannot find something, you explain why and suggest alternatives."
            )

agent = MyCustomAgent(
    data_dir=os.getenv("DATA_DIR", "core/data"),
    chroma_path=os.getenv("CHROMA_PATH", "./chroma_db"),
)
asyncio.run(agent.run())
```

Here, you’re reusing all the core planning, reasoning, and execution logic —  
just plugging in your own **personality, actions, and task documents**.

---

## 🧩 Architecture Overview

| Component | Description |
|------------|-------------|
| **BaseAgent** | The core reasoning and execution engine — can be subclassed or used directly. |
| **Action / Tool** | Reusable atomic functions (e.g., web search, API calls, file ops). |
| **Task Document** | Describes what the agent must achieve and how. |
| **Planner / Executor** | Handles goal decomposition, script generation, and execution. |
| **LLM Wrapper** | Unified layer for model interactions (OpenAI, Gemini, etc.). |

---

## 🤝 How to Contribute

Contributions and suggestions are welcome! You can contact [@zfoong](https://github.com/zfoong) @ thamyikfoong(at)craftos.net. We currently don't have checks set up, so we can't allow direct contributions but we appreciate any suggestions and feedback.

## 🧾 License

This project is licensed under the [MIT License](LICENSE). You are free to use, host, and monetize this project (you must credit this project in case of distribution and monetization).

---

## ⭐ Acknowledgements

Developed and maintained by [CraftOS](https://craftos.net/) and contributors [@zfoong](https://github.com/zfoong) and [@ahmad-ajmal](https://github.com/ahmad-ajmal).  
If you find **CraftBot** useful, please ⭐ the repository and share it with others!

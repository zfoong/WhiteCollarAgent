<div align="center">
    <img src="assets/craftos_mascot.png" alt="CraftOS 标志" width="200"/>
</div>
<br>

<h1 align="center">白领AI代理（CraftBot）</h1>

<div align="center">
  <img src="https://img.shields.io/badge/OS-Windows-blue?logo=windows&logoColor=white" alt="Windows">
  <img src="https://img.shields.io/badge/OS-Linux-yellow?logo=linux&logoColor=black" alt="Linux">

  <a href="https://github.com/zfoong/CraftBot">
    <img src="https://img.shields.io/github/stars/zfoong/CraftBot?style=social" alt="GitHub Repo stars">
  </a>

  <img src="https://img.shields.io/github/license/zfoong/CraftBot" alt="License">

  <a href="https://discord.gg/ZN9YHc37HG">
    <img src="https://img.shields.io/badge/Discord-%E5%8A%A0%E5%85%A5%E7%A4%BE%E5%8C%BA-5865F2?logo=discord&logoColor=white" alt="Discord">
  </a>

</div>

---

<p align="center">
  <a href="README.md"> 英语版README </a> | <a href="README.jp.md"> 日语版README </a>
</p>

## 🚀 概览

**CraftBot** 是一个极简但强大的computer-use AI 代理。它能够完成一系列复杂的电脑端与浏览器端任务。
它可以自主理解任务、规划行动并执行操作，以实现复杂目标。
它会根据任务性质在 CLI 与 GUI 模式之间切换。
本代码也可作为你构建自定义AI代理的基础框架。

你可以：

* 🧠 使用**内置代理**自动规划并执行复杂任务链
* 🧩 通过**继承基础代码**来构建专用的代理行为或工作流
* 💻 通过**TUI 界面**与代理交互

<div align="center">
    <img src="assets/white_collar_agent_demo.PNG" alt="演示" width="720"/>
</div>

这使它成为研究人员与开发者探索**系统级代理式 AI**、**运行时代码生成**与**自主执行**以自动化工作流、产出结果的理想工具。
这是一个开源项目，仍在开发中，我们欢迎任何建议、贡献与反馈。你可以自由使用、部署并将其商业化（在分发与商业化时需注明来源）。

---

## ✨ 特性

* 🧠 **单一基础代理架构** — 简洁且可扩展的核心，负责推理、规划与执行
* ⚙️ **CLI/GUI 模式** — 代理可根据任务复杂度在 CLI 与 GUI 间切换。GUI 模式仍处于实验阶段 🧪
* 🧩 **继承与扩展** — 通过继承基类构建你自己的代理
* 🔍 **任务文档接口** — 用结构化任务定义让代理进行上下文学习（in-context learning）
* 🧰 **动作库（Action library）** — 可复用工具（网页搜索、代码执行、I/O 等）
* 🪶 **轻量且跨平台** — 在 Linux 与 Windows 上无缝运行

> [!IMPORTANT]
> **关于 GUI 模式的说明：** GUI 模式仍处于实验阶段。代理切换到 GUI 模式时会有些问题。我们仍在持续完善。

## 🔜 路线图

* [ ] **记忆模块** — 下一步推出！
* [ ] **外部工具集成** — 待定
* [ ] **MCP 层** — 待定
* [ ] **主动式行为** — 待定

---

## 🧰 环境设置

### 前置要求

* Python **3.9+**
* `git`、`conda`、`pip`
* 你所选 LLM 提供商的 API Key（例如 OpenAI 或 Gemini）

### 安装

```bash
git clone https://github.com/zfoong/CraftBot.git
cd CraftBot
conda env create -f environment.yml
```

---

## ⚡ 快速上手

导出你的 API Key：

```bash
export OPENAI_API_KEY=<YOUR_KEY_HERE>
or
export GOOGLE_API_KEY=<YOUR_KEY_HERE>
```

运行 CLI 工具：

```bash
python -m core.main
```

这会启动内置的 **CraftBot**，让你可以与它沟通：

1. 与AI代理对话
2. 让它执行复杂的任务序列
3. 运行命令 `/help` 获取帮助
4. 与AI代理一起协作

---

## 使用container运行

repository root 目录包含 Docker 配置：使用 Python 3.10、关键系统依赖（包含用于 OCR 的 Tesseract），以及在 `environment.yml`/`requirements.txt` 中定义的所有 Python 库，从而让代理在隔离环境中保持一致运行。

下面是在container中运行AI代理的配置步骤。

### 构建image

在repository root执行：

```bash
docker build -t craftbot .
```

### 运行container

image默认会用 `python -m core.main` 启动AI代理。要交互式运行：

```bash
docker run --rm -it craftbot
```

如果需要传入环境变量，可使用 env 文件（例如基于 `.env.example`）：

```bash
docker run --rm -it --env-file .env craftbot
```

使用 `-v` 挂载需要在container外持久化的目录（例如数据或缓存文件夹），并根据部署需要调整端口或额外参数。该容器内置 OCR（`tesseract`）、屏幕自动化（`pyautogui`、`mss`、X11 工具与虚拟帧缓冲）以及常见 HTTP 客户端等系统依赖，使代理能够在容器中处理文件、网络 API 与 GUI 自动化。

### 启用GUI自动化

GUI 操作（鼠标/键盘事件、截图）需要 X11 服务器。你可以连接宿主机显示，或使用 `xvfb` 无头运行：

* 使用宿主机显示（需要带 X11 的 Linux）：

  ```bash
  docker run --rm -it 
    -e DISPLAY=$DISPLAY \
    -v /tmp/.X11-unix:/tmp/.X11-unix \
    -v $(pwd)/data:/app/core/data \
    craftbot
  ```

  如需让代理读写更多目录，可添加额外的 `-v` 挂载。

* 使用虚拟显示进行headless运行：

  ```bash
    docker run --rm -it --env-file .env craftbot bash -lc "Xvfb :99 -screen 0 1920x1080x24 & export DISPLAY=:99 && exec python -m core.main"
  ```

默认情况下image会使用 Python 3.10，并打包了 `environment.yml`/`requirements.txt` 中的 Python 依赖，因此 `python -m core.main` 可开箱即用。

---

## 🧠 示例：构建自定义代理

你可以通过扩展底层AI代理轻松创建专用代理：

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

在这里，你复用了全部核心的规划、推理与执行逻辑——
只需要接入你自己定义的**AI个性、动作与任务文档**即可。

---

## 🧩 架构概览

| 组件                     | 说明                            |
| ---------------------- | ----------------------------- |
| **BaseAgent**          | 核心推理与执行引擎——可直接使用或通过继承扩展。      |
| **Action / Tool**      | 可复用的原子功能（例如网页搜索、API 调用、文件操作）。 |
| **Task Document**      | 描述AI代理需要达成的目标与方式。             |
| **Planner / Executor** | 负责目标拆解、脚本生成与执行。               |
| **LLM Wrapper**        | 统一的模型交互层（OpenAI、Gemini 等）。    |

---

## 🤝 如何贡献

欢迎各种建议与反馈！你可以联系 [@zfoong](https://github.com/zfoong)，邮箱为 thamyikfoong(at)craftos.net。我们目前尚未配置检查流程，因此无法接受直接提交贡献，但非常感谢你的建议与反馈。
也欢迎你加入我们的Discord群： https://discord.gg/ZN9YHc37HG

## 🧾 许可证

本项目采用 [MIT License](LICENSE) 许可。你可以自由使用、部署并将其商业化（在分发与商业化时必须注明本项目来源/致谢）。

---

## ⭐ 致谢

由 [CraftOS](https://craftos.net/) 与贡献者 [@zfoong](https://github.com/zfoong) 及 [@ahmad-ajmal](https://github.com/ahmad-ajmal) 开发与维护。
如果你觉得 **CraftBot** 有用，请给仓库点一个 ⭐ 并分享给更多人。

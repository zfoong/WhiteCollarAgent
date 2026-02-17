<div align="center">
    <img src="assets/craftos_mascot.png" alt="CraftOS Logo" width="200"/>
</div>
<br>

<h1 align="center">CraftBot</h1>

<div align="center">
  <img src="https://img.shields.io/badge/OS-Windows-blue?logo=windows&logoColor=white" alt="Windows">
  <img src="https://img.shields.io/badge/OS-Linux-yellow?logo=linux&logoColor=black" alt="Linux">
  
  <a href="https://github.com/zfoong/CraftBot">
    <img src="https://img.shields.io/github/stars/zfoong/CraftBot?style=social" alt="GitHub Repo stars">
  </a>

  <img src="https://img.shields.io/github/license/zfoong/CraftBot" alt="License">

  <a href="https://discord.gg/MRmjubap">
    <img src="https://img.shields.io/badge/Discord-Join%20the%20community-5865F2?logo=discord&logoColor=white" alt="Discord">
  </a>
  
</div>



---
<p align="center">
  <a href="README.md">🇬🇧 English version here</a>
</p>

## 🚀 概要

**CraftBot**は、複雑なコンピュータベースおよびブラウザベースのタスクを一連で実行できる、ミニマルでありながら強力なコンピュータ利用型AIエージェントです。  
タスクを自律的に解釈し、アクションを計画し、複雑な目標を達成するためにアクションを実行できます。
タスクの性質に応じて、CLIモードとGUIモードを切り替えることができます。 
このコードは、独自のインテリジェントエージェントを構築するための基盤としても機能します。

ユーザーは以下のことができます:
- 🧠 **組み込みエージェント**を使用して、複雑な一連のタスクを自動的に計画・実行  
- 🧩 **ベースエージェントをサブクラス化**して、独自の専門的なエージェントの動作やワークフローを構築
- 💻 **TUIインターフェース**でエージェントと対話

<div align="center">
    <img src="assets/white_collar_agent_demo.PNG" alt="Demo" width="720"/>
</div>

これにより、**システムベースのエージェンティックAI**、**ランタイムコード生成**、**自律実行**を探求する組織、研究者、開発者にとって、ワークフローを自動化し、結果を達成するための理想的なツールとなっています。
これはオープンソースプロジェクトであり、まだ開発中ですので、提案、貢献、フィードバックを歓迎します！このプロジェクトは自由に使用、ホスト、収益化できます（配布や収益化の場合はクレジット表記が必要です）。

---

## ✨ 特徴

- 🧠 **単一ベースエージェントアーキテクチャ** — 推論、計画、実行を処理するシンプルで拡張可能なコア。  
- ⚙️ **CLI/GUIモード** — エージェントはタスクの複雑さに応じてCLIモードとGUIモードを切り替えることができます。GUIモードはまだ実験段階です 🧪。
- 🧩 **サブクラス化と拡張** — ベースクラスを継承して独自のエージェントを構築。  
- 🔍 **タスクドキュメントインターフェース** — エージェントがコンテキスト内学習を実行するための構造化されたタスクを定義。  
- 🧰 **アクションライブラリ** — 再利用可能なツール（Web検索、コード実行、I/Oなど）。  
- 🪶 **軽量でクロスプラットフォーム** — LinuxとWindowsでシームレスに動作。

> [!IMPORTANT]
> **GUIモードに関する注意:** GUIモードはまだ実験段階です。これは、エージェントがGUIモードに切り替えることを決定した場合、多くの問題に遭遇することを意味します。現在も改善に取り組んでいます。

## 🔜 ロードマップ

- [ ] **メモリモジュール** — 次回実装予定
- [ ] **外部ツール統合** — 実装予定
- [ ] **MCPレイヤー** — 実装予定
- [ ] **プロアクティブな動作** — 実装予定

---

## 🧰 はじめに

### 前提条件
- Python **3.9+**
- `git`、`conda`、`pip`
- 選択したLLMプロバイダー（OpenAIやGeminiなど）のAPIキー

### インストール
```bash
git clone https://github.com/zfoong/CraftBot.git
cd CraftBot
conda env create -f environment.yml
```

---

## ⚡ クイックスタート

APIキーをエクスポート:
```bash
export OPENAI_API_KEY=<YOUR_KEY_HERE>
or
export GOOGLE_API_KEY=<YOUR_KEY_HERE>
```

CLIツールを実行:
```bash
python -m core.main
```

これにより、組み込みの**CraftBot**が実行され、以下のことができます:
1. エージェントと会話  
2. 複雑な一連のタスクを実行するよう依頼  
3. /helpコマンドを実行してヘルプを求める
4. AIエージェントと仲良くなる

---

## コンテナで実行

リポジトリのルートには、Python 3.10、主要なシステムパッケージ（OCR用のTesseractを含む）、および`environment.yml`/`requirements.txt`で定義されたすべてのPython依存関係を含むDocker構成が含まれており、エージェントは隔離された環境で一貫して実行できます。 

以下は、コンテナでエージェントを実行するためのセットアップ手順です。

### イメージのビルド

リポジトリのルートから:

```bash
docker build -t craftbot .
```

### コンテナの実行

イメージはデフォルトで`python -m core.main`でエージェントを起動するように構成されています。対話的に実行するには:

```bash
docker run --rm -it craftbot
```

環境変数を渡す必要がある場合は、envファイル（例えば`.env.example`に基づく）を渡します:

```bash
docker run --rm -it --env-file .env craftbot
```

コンテナの外部で永続化する必要があるディレクトリ（データやキャッシュフォルダなど）は`-v`を使用してマウントし、デプロイに必要に応じてポートや追加のフラグを調整してください。コンテナには、OCR（`tesseract`）、画面自動化（`pyautogui`、`mss`、X11ユーティリティ、仮想フレームバッファ）、および一般的なHTTPクライアント用のシステム依存関係が含まれているため、エージェントはコンテナ内でファイル、ネットワークAPI、GUI自動化を扱うことができます。

### GUI/画面自動化の有効化

GUIアクション（マウス/キーボードイベント、スクリーンショット）にはX11サーバーが必要です。ホストディスプレイにアタッチするか、`xvfb`でヘッドレスで実行できます:

* ホストディスプレイを使用（X11を使用するLinuxが必要）:

  ```bash
  docker run --rm -it \
    -e DISPLAY=$DISPLAY \
    -v /tmp/.X11-unix:/tmp/.X11-unix \
    -v $(pwd)/data:/app/core/data \
    craftbot
  ```

  エージェントが読み書きする必要があるフォルダには、追加の`-v`マウントを追加してください。

* 仮想ディスプレイでヘッドレス実行:

```bash
docker run --rm -it --env-file .env craftbot bash -lc "Xvfb :99 -screen 0 1920x1080x24 & export DISPLAY=:99 && exec python -m core.main"
```

デフォルトでは、イメージはPython 3.10を使用し、`environment.yml`/`requirements.txt`からのPython依存関係をバンドルしているため、`python -m core.main`はそのまま動作します。

---

## 🧠 例: カスタムエージェントの構築

ベースエージェントを拡張することで、独自の専門的なエージェントを簡単に作成できます:

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
            このエージェントの役割、動作、目的を定義します。
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

ここでは、すべてのコア計画、推論、実行ロジックを再利用しています —  
独自の**パーソナリティ、アクション、タスクドキュメント**を組み込むだけです。

---

## 🧩 アーキテクチャの概要

| コンポーネント | 説明 |
|------------|-------------|
| **BaseAgent** | コア推論および実行エンジン — サブクラス化または直接使用可能。 |
| **Action / Tool** | 再利用可能なアトミック関数（例: Web検索、API呼び出し、ファイル操作）。 |
| **Task Document** | エージェントが達成すべきことと方法を記述。 |
| **Planner / Executor** | 目標の分解、スクリプト生成、実行を処理。 |
| **LLM Wrapper** | モデルインタラクション用の統一レイヤー（OpenAI、Geminiなど）。 |

---

## 🤝 貢献方法

貢献と提案を歓迎します！[@zfoong](https://github.com/zfoong) @ thamyikfoong(at)craftos.net までご連絡ください。現在、チェック機能を設定していないため、直接的な貢献は受け付けられませんが、提案やフィードバックは大変ありがたく思います。

## 🧾 ライセンス

このプロジェクトは[MITライセンス](LICENSE)の下でライセンスされています。このプロジェクトは自由に使用、ホスト、収益化できます（配布や収益化の場合は、このプロジェクトのクレジット表記が必要です）。

---

## ⭐ 謝辞

[CraftOS](https://craftos.net/)および貢献者[@zfoong](https://github.com/zfoong)と[@ahmad-ajmal](https://github.com/ahmad-ajmal)によって開発・維持されています。  
**CraftBot**が役に立つと思われた場合は、リポジトリに⭐をつけて、他の人と共有してくださると嬉しいです！

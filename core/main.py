# -*- coding: utf-8 -*-
"""
core.main

Main driver code that starts the **vanilla BaseAgent**.
Environment variables let you tweak connection details without code
changes, making this usable inside Docker containers.

Run this before the core directory, using 'python -m core.main'
"""

import asyncio
import os
from dotenv import load_dotenv
load_dotenv()

from core.agent_base import AgentBase
from core.menu_interface import MenuInterface


async def _async_main() -> None:
    menu = MenuInterface()
    menu_choice = await menu.show()

    if menu_choice.action == "exit":
        return

    menu.apply_api_key(menu_choice.provider, menu_choice.api_key)

    agent = AgentBase(
        data_dir=os.getenv("DATA_DIR", "core/data"),
        chroma_path=os.getenv("CHROMA_PATH", "./chroma_db"),
        provider=menu_choice.provider,
    )
    await agent.run()


def main() -> None:
    asyncio.run(_async_main())


if __name__ == "__main__":
    main()

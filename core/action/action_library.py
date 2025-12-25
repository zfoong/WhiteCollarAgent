# -*- coding: utf-8 -*-
"""
Updated ActionLibrary that delegates database operations
to the new DatabaseInterface.

Created on Thu Mar 27 21:29:03 2025
Author: zfoong
"""

import datetime
import json
from typing import List, Optional

from core.database_interface import DatabaseInterface
from core.action.action import Action
from core.logger import logger

class ActionLibrary:
    """
    Manages storing, retrieving, and modifying actions via DatabaseInterface.
    """

    def __init__(self, llm_interface, db_interface: DatabaseInterface):
        """
        Initialize the library responsible for persisting actions.

        Args:
            llm_interface: LLM client used elsewhere for generating actions.
            db_interface: Database gateway that handles MongoDB/ChromaDB storage.
        """
        self.llm_interface = llm_interface
        self.db_interface = db_interface

    def store_action(self, action: Action):
        """
        Persist an action definition and stamp its update time.

        Args:
            action: Action instance to serialize and store.
        """
        action_dict = action.to_dict()
        action_dict["updatedAt"] = datetime.datetime.utcnow().isoformat()
        self.db_interface.store_action(action_dict)

    def sync_databases(self):
        """
        Ensures that all actions stored in data/actions folder are present in ChromaDB.
        If an action is missing from ChromaDB, it will be added.
        """
        logger.debug("Syncing MongoDB and ChromaDB...")
        added_count = self.db_interface.sync_actions_to_chroma()
        if added_count > 0:
            logger.debug(f"Added {added_count} missing actions to ChromaDB.")
        else:
            logger.debug("Databases are already in sync. No missing actions found.")

    def retrieve_action(self, action_name: str) -> Optional[Action]:
        """
        Fetch a single action by name.

        Args:
            action_name: Case-insensitive name of the action to retrieve.

        Returns:
            Optional[Action]: Hydrated action instance if found, otherwise ``None``.
        """
        action_data = self.db_interface.get_action(action_name)
        if action_data:
            return Action.from_dict(action_data)
        return None

    def retrieve_default_action(self) -> List[Action]:
        """
        Retrieve actions marked as defaults.
        These actions are always available to the agents regardless of the mode.

        Returns:
            List[Action]: All default actions stored in the database.
        """
        docs = self.db_interface.list_actions(default=True)
        return [Action.from_dict(doc) for doc in docs]

    def get_default_action_names(self) -> set[str]:
        return {
            action.name
            for action in self.retrieve_default_action()
        }

    def search_action(self, query: str, top_k=50) -> List[str]:
        """
        Search for actions using vector similarity.

        Args:
            query: Natural-language description of the desired action.
            top_k: Maximum number of action names to return.

        Returns:
            List[str]: Ranked list of matching action names.
        """
        return self.db_interface.search_actions(query, top_k)

    def delete_action(self, action_name: str):
        """Deletes an action from both MongoDB and ChromaDB."""
        self.db_interface.delete_action(action_name)

from typing import Optional, Dict, Any
from core.external_libraries.external_app_library import ExternalAppLibrary
from core.external_libraries.credential_store import CredentialsStore
from core.external_libraries.recall.credentials import RecallCredential
from core.external_libraries.recall.helpers.recall_helpers import (
    create_bot,
    get_bot,
    list_bots,
    delete_bot,
    leave_meeting,
    send_chat_message,
    get_transcript,
    get_recording,
    output_audio,
)


class RecallAppLibrary(ExternalAppLibrary):
    """
    Recall.ai integration library for the CraftOS agent system.

    Recall.ai provides meeting bot infrastructure that can:
    - Join Zoom, Google Meet, and Microsoft Teams meetings
    - Record meetings
    - Transcribe in real-time
    - Send chat messages
    - Output audio (speak in meetings)

    This enables the agent to:
    - Attend meetings on behalf of users
    - Take notes and create summaries
    - Participate in discussions
    - Answer questions in real-time
    """

    _name = "Recall"
    _version = "1.0.0"
    _credential_store: Optional[CredentialsStore] = None
    _initialized: bool = False

    @classmethod
    def initialize(cls):
        """Initialize the Recall library with its own credential store."""
        if cls._initialized:
            return

        cls._credential_store = CredentialsStore(
            credential_cls=RecallCredential,
            persistence_file="recall_credentials.json",
        )
        cls._initialized = True

    @classmethod
    def get_name(cls) -> str:
        return cls._name

    @classmethod
    def get_credential_store(cls) -> CredentialsStore:
        if cls._credential_store is None:
            raise RuntimeError("RecallAppLibrary not initialized. Call initialize() first.")
        return cls._credential_store

    @classmethod
    def validate_connection(cls, user_id: str) -> bool:
        """Check if Recall.ai credentials exist for the given user."""
        cred_store = cls.get_credential_store()
        credentials = cred_store.get(user_id=user_id)
        return len(credentials) > 0

    @classmethod
    def get_credentials(cls, user_id: str) -> Optional[RecallCredential]:
        """Retrieve Recall.ai credential for the given user."""
        cred_store = cls.get_credential_store()
        credentials = cred_store.get(user_id=user_id)
        if credentials:
            return credentials[0]
        return None

    # ═══════════════════════════════════════════════════════════════════════════
    # BOT MANAGEMENT
    # ═══════════════════════════════════════════════════════════════════════════

    @classmethod
    def join_meeting(
        cls,
        user_id: str,
        meeting_url: str,
        bot_name: str = "Meeting Assistant",
        transcription_provider: str = "deepgram",
        recording_mode: str = "speaker_view",
    ) -> Dict[str, Any]:
        """
        Deploy a bot to join a meeting.

        Args:
            user_id: CraftOS user ID
            meeting_url: URL of the meeting (Zoom, Google Meet, Teams)
            bot_name: Display name for the bot
            transcription_provider: "deepgram" or "assembly_ai"
            recording_mode: "speaker_view", "gallery_view", or "audio_only"

        Returns:
            Bot details including bot_id for tracking
        """
        try:
            credential = cls.get_credentials(user_id=user_id)
            if not credential:
                return {"status": "error", "reason": "No Recall.ai API key found. Please configure your API key."}

            transcription_options = {"provider": transcription_provider}

            result = create_bot(
                api_key=credential.api_key,
                meeting_url=meeting_url,
                bot_name=bot_name,
                transcription_options=transcription_options,
                recording_mode=recording_mode,
                region=credential.region,
            )

            if "error" in result:
                return {"status": "error", "details": result}

            return {"status": "success", "bot": result.get("result")}

        except Exception as e:
            return {"status": "error", "reason": f"Unexpected error: {str(e)}"}

    @classmethod
    def get_bot_status(
        cls,
        user_id: str,
        bot_id: str,
    ) -> Dict[str, Any]:
        """
        Get the current status of a meeting bot.

        Args:
            user_id: CraftOS user ID
            bot_id: The bot ID returned from join_meeting

        Returns:
            Bot status, participants, and other details
        """
        try:
            credential = cls.get_credentials(user_id=user_id)
            if not credential:
                return {"status": "error", "reason": "No Recall.ai API key found."}

            result = get_bot(
                api_key=credential.api_key,
                bot_id=bot_id,
                region=credential.region,
            )

            if "error" in result:
                return {"status": "error", "details": result}

            return {"status": "success", "bot": result.get("result")}

        except Exception as e:
            return {"status": "error", "reason": f"Unexpected error: {str(e)}"}

    @classmethod
    def list_bots(
        cls,
        user_id: str,
        page_size: int = 50,
    ) -> Dict[str, Any]:
        """
        List all meeting bots.

        Args:
            user_id: CraftOS user ID
            page_size: Number of bots per page

        Returns:
            List of bots with their statuses
        """
        try:
            credential = cls.get_credentials(user_id=user_id)
            if not credential:
                return {"status": "error", "reason": "No Recall.ai API key found."}

            result = list_bots(
                api_key=credential.api_key,
                page_size=page_size,
                region=credential.region,
            )

            if "error" in result:
                return {"status": "error", "details": result}

            return {"status": "success", "bots": result.get("result")}

        except Exception as e:
            return {"status": "error", "reason": f"Unexpected error: {str(e)}"}

    @classmethod
    def leave_meeting(
        cls,
        user_id: str,
        bot_id: str,
    ) -> Dict[str, Any]:
        """
        Make a bot leave the meeting.

        Args:
            user_id: CraftOS user ID
            bot_id: The bot ID

        Returns:
            Success status
        """
        try:
            credential = cls.get_credentials(user_id=user_id)
            if not credential:
                return {"status": "error", "reason": "No Recall.ai API key found."}

            result = leave_meeting(
                api_key=credential.api_key,
                bot_id=bot_id,
                region=credential.region,
            )

            if "error" in result:
                return {"status": "error", "details": result}

            return {"status": "success", "result": result.get("result")}

        except Exception as e:
            return {"status": "error", "reason": f"Unexpected error: {str(e)}"}

    @classmethod
    def delete_bot(
        cls,
        user_id: str,
        bot_id: str,
    ) -> Dict[str, Any]:
        """
        Delete a bot and its data.

        Args:
            user_id: CraftOS user ID
            bot_id: The bot ID

        Returns:
            Success status
        """
        try:
            credential = cls.get_credentials(user_id=user_id)
            if not credential:
                return {"status": "error", "reason": "No Recall.ai API key found."}

            result = delete_bot(
                api_key=credential.api_key,
                bot_id=bot_id,
                region=credential.region,
            )

            if "error" in result:
                return {"status": "error", "details": result}

            return {"status": "success", "deleted": True}

        except Exception as e:
            return {"status": "error", "reason": f"Unexpected error: {str(e)}"}

    # ═══════════════════════════════════════════════════════════════════════════
    # TRANSCRIPTION & RECORDING
    # ═══════════════════════════════════════════════════════════════════════════

    @classmethod
    def get_transcript(
        cls,
        user_id: str,
        bot_id: str,
    ) -> Dict[str, Any]:
        """
        Get the meeting transcript.

        Args:
            user_id: CraftOS user ID
            bot_id: The bot ID

        Returns:
            Transcript with speaker labels and timestamps
        """
        try:
            credential = cls.get_credentials(user_id=user_id)
            if not credential:
                return {"status": "error", "reason": "No Recall.ai API key found."}

            result = get_transcript(
                api_key=credential.api_key,
                bot_id=bot_id,
                region=credential.region,
            )

            if "error" in result:
                return {"status": "error", "details": result}

            return {"status": "success", "transcript": result.get("result", {}).get("transcript")}

        except Exception as e:
            return {"status": "error", "reason": f"Unexpected error: {str(e)}"}

    @classmethod
    def get_recording(
        cls,
        user_id: str,
        bot_id: str,
    ) -> Dict[str, Any]:
        """
        Get the meeting recording URL.

        Args:
            user_id: CraftOS user ID
            bot_id: The bot ID

        Returns:
            Recording video URL
        """
        try:
            credential = cls.get_credentials(user_id=user_id)
            if not credential:
                return {"status": "error", "reason": "No Recall.ai API key found."}

            result = get_recording(
                api_key=credential.api_key,
                bot_id=bot_id,
                region=credential.region,
            )

            if "error" in result:
                return {"status": "error", "details": result}

            return {"status": "success", "recording": result.get("result")}

        except Exception as e:
            return {"status": "error", "reason": f"Unexpected error: {str(e)}"}

    # ═══════════════════════════════════════════════════════════════════════════
    # INTERACTION
    # ═══════════════════════════════════════════════════════════════════════════

    @classmethod
    def send_chat_message(
        cls,
        user_id: str,
        bot_id: str,
        message: str,
    ) -> Dict[str, Any]:
        """
        Send a chat message in the meeting.

        Args:
            user_id: CraftOS user ID
            bot_id: The bot ID
            message: Message to send in the meeting chat

        Returns:
            Success status
        """
        try:
            credential = cls.get_credentials(user_id=user_id)
            if not credential:
                return {"status": "error", "reason": "No Recall.ai API key found."}

            result = send_chat_message(
                api_key=credential.api_key,
                bot_id=bot_id,
                message=message,
                region=credential.region,
            )

            if "error" in result:
                return {"status": "error", "details": result}

            return {"status": "success", "sent": True, "message": message}

        except Exception as e:
            return {"status": "error", "reason": f"Unexpected error: {str(e)}"}

    @classmethod
    def speak_in_meeting(
        cls,
        user_id: str,
        bot_id: str,
        audio_data: str,
        audio_format: str = "wav",
    ) -> Dict[str, Any]:
        """
        Output audio through the bot (speak in the meeting).

        Args:
            user_id: CraftOS user ID
            bot_id: The bot ID
            audio_data: Base64 encoded audio data
            audio_format: Audio format ("wav", "mp3")

        Returns:
            Success status
        """
        try:
            credential = cls.get_credentials(user_id=user_id)
            if not credential:
                return {"status": "error", "reason": "No Recall.ai API key found."}

            result = output_audio(
                api_key=credential.api_key,
                bot_id=bot_id,
                audio_data=audio_data,
                audio_format=audio_format,
                region=credential.region,
            )

            if "error" in result:
                return {"status": "error", "details": result}

            return {"status": "success", "audio_sent": True}

        except Exception as e:
            return {"status": "error", "reason": f"Unexpected error: {str(e)}"}

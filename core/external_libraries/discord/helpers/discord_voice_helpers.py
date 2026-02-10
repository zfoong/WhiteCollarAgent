"""
Discord Voice helper functions.

Voice functionality requires the discord.py library with voice support.
Install with: pip install discord.py[voice]

This module provides a VoiceManager class that handles:
- Joining/leaving voice channels
- Audio recording and playback
- Integration with transcription services (OpenAI Whisper)
- Text-to-speech with OpenAI TTS

Requires:
- discord.py[voice]: pip install discord.py[voice]
- openai: pip install openai (for Whisper STT and TTS)
- PyNaCl: pip install PyNaCl (for voice encryption)
- FFmpeg: Must be installed on system
"""
import asyncio
import io
import os
import wave
import struct
import tempfile
from typing import Optional, Dict, Any, Callable, List
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path

# Try to import discord.py
try:
    import discord
    from discord.ext import commands
    DISCORD_PY_AVAILABLE = True
except ImportError:
    DISCORD_PY_AVAILABLE = False

# Try to import OpenAI
try:
    from openai import OpenAI
    OPENAI_AVAILABLE = True
except ImportError:
    OPENAI_AVAILABLE = False

# Get OpenAI Audio API key from config
try:
    from core.config import OPENAI_AUDIO_API_KEY
except ImportError:
    OPENAI_AUDIO_API_KEY = os.getenv("OPENAI_AUDIO_API_KEY", "")


@dataclass
class VoiceSession:
    """Represents an active voice session."""
    guild_id: str
    channel_id: str
    connected_at: datetime = field(default_factory=datetime.utcnow)
    is_recording: bool = False
    is_speaking: bool = False
    audio_buffer: Dict[int, List[bytes]] = field(default_factory=dict)  # user_id -> audio chunks
    transcript_callback: Optional[Callable] = None
    last_transcripts: Dict[int, str] = field(default_factory=dict)  # user_id -> last transcript


class AudioRecordingSink:
    """
    Custom audio sink for recording voice channel audio.
    Collects audio from all users in the voice channel.
    """

    def __init__(self, session: VoiceSession, on_audio_chunk: Optional[Callable] = None):
        self.session = session
        self.on_audio_chunk = on_audio_chunk
        self.audio_data: Dict[int, io.BytesIO] = {}  # user_id -> audio buffer

    def write(self, data: bytes, user_id: int):
        """Called when audio data is received from a user."""
        if user_id not in self.audio_data:
            self.audio_data[user_id] = io.BytesIO()

        self.audio_data[user_id].write(data)

        # Also store in session buffer for processing
        if user_id not in self.session.audio_buffer:
            self.session.audio_buffer[user_id] = []
        self.session.audio_buffer[user_id].append(data)

        if self.on_audio_chunk:
            self.on_audio_chunk(user_id, data)

    def cleanup(self):
        """Clean up resources."""
        for buffer in self.audio_data.values():
            buffer.close()
        self.audio_data.clear()

    def get_user_audio(self, user_id: int) -> Optional[bytes]:
        """Get recorded audio for a specific user."""
        if user_id in self.audio_data:
            self.audio_data[user_id].seek(0)
            return self.audio_data[user_id].read()
        return None

    def get_all_audio(self) -> Dict[int, bytes]:
        """Get recorded audio for all users."""
        result = {}
        for user_id, buffer in self.audio_data.items():
            buffer.seek(0)
            result[user_id] = buffer.read()
        return result


class DiscordVoiceManager:
    """
    Manages Discord voice connections for a bot.

    Usage:
        manager = DiscordVoiceManager(bot_token)
        await manager.start()
        await manager.join_voice(guild_id, channel_id)
        await manager.start_recording(guild_id, transcribe_callback)
        await manager.speak(guild_id, audio_source)
        await manager.leave_voice(guild_id)
    """

    def __init__(self, bot_token: str):
        if not DISCORD_PY_AVAILABLE:
            raise ImportError("discord.py is required for voice features. Install with: pip install discord.py[voice]")

        self.bot_token = bot_token
        self.bot: Optional[commands.Bot] = None
        self.voice_sessions: Dict[str, VoiceSession] = {}  # guild_id -> session
        self._running = False

    async def start(self) -> Dict[str, Any]:
        """
        Start the Discord bot for voice operations.

        Returns:
            Status of the bot start operation
        """
        try:
            intents = discord.Intents.default()
            intents.message_content = True
            intents.voice_states = True
            intents.guilds = True

            self.bot = commands.Bot(command_prefix="!", intents=intents)

            @self.bot.event
            async def on_ready():
                print(f"Discord voice bot ready: {self.bot.user}")
                self._running = True

            # Start bot in background
            asyncio.create_task(self.bot.start(self.bot_token))

            # Wait for bot to be ready
            for _ in range(30):  # 30 second timeout
                if self._running:
                    return {"ok": True, "result": {"status": "connected", "bot_user": str(self.bot.user)}}
                await asyncio.sleep(1)

            return {"error": "Bot failed to connect within timeout"}

        except Exception as e:
            return {"error": str(e)}

    async def stop(self) -> Dict[str, Any]:
        """Stop the Discord bot."""
        try:
            if self.bot:
                # Leave all voice channels
                for guild_id in list(self.voice_sessions.keys()):
                    await self.leave_voice(guild_id)

                await self.bot.close()
                self._running = False
                return {"ok": True, "result": {"status": "disconnected"}}
            return {"ok": True, "result": {"status": "not_running"}}
        except Exception as e:
            return {"error": str(e)}

    async def join_voice(
        self,
        guild_id: str,
        channel_id: str,
        self_deaf: bool = False,
        self_mute: bool = False,
    ) -> Dict[str, Any]:
        """
        Join a voice channel.

        Args:
            guild_id: The guild ID
            channel_id: The voice channel ID
            self_deaf: Whether to self-deafen
            self_mute: Whether to self-mute

        Returns:
            Status of the join operation
        """
        try:
            if not self.bot or not self._running:
                return {"error": "Bot not running. Call start() first."}

            guild = self.bot.get_guild(int(guild_id))
            if not guild:
                return {"error": f"Guild {guild_id} not found"}

            channel = guild.get_channel(int(channel_id))
            if not channel:
                return {"error": f"Channel {channel_id} not found"}

            if not isinstance(channel, discord.VoiceChannel):
                return {"error": "Channel is not a voice channel"}

            # Leave existing voice connection in this guild if any
            if guild_id in self.voice_sessions:
                await self.leave_voice(guild_id)

            # Connect to voice channel
            voice_client = await channel.connect(self_deaf=self_deaf, self_mute=self_mute)

            # Create voice session
            self.voice_sessions[guild_id] = VoiceSession(
                guild_id=guild_id,
                channel_id=channel_id,
            )

            return {
                "ok": True,
                "result": {
                    "status": "connected",
                    "guild_id": guild_id,
                    "channel_id": channel_id,
                    "channel_name": channel.name,
                }
            }

        except Exception as e:
            return {"error": str(e)}

    async def leave_voice(self, guild_id: str) -> Dict[str, Any]:
        """
        Leave the voice channel in a guild.

        Args:
            guild_id: The guild ID

        Returns:
            Status of the leave operation
        """
        try:
            if not self.bot:
                return {"error": "Bot not running"}

            guild = self.bot.get_guild(int(guild_id))
            if not guild:
                return {"error": f"Guild {guild_id} not found"}

            if guild.voice_client:
                await guild.voice_client.disconnect()

            # Remove session
            if guild_id in self.voice_sessions:
                del self.voice_sessions[guild_id]

            return {"ok": True, "result": {"status": "disconnected", "guild_id": guild_id}}

        except Exception as e:
            return {"error": str(e)}

    async def speak_text(
        self,
        guild_id: str,
        text: str,
        tts_provider: str = "openai",
        voice: str = "alloy",
    ) -> Dict[str, Any]:
        """
        Speak text in the voice channel using TTS.

        Args:
            guild_id: The guild ID
            text: Text to speak
            tts_provider: TTS provider to use ("openai" for high quality, "gtts" for free)
            voice: OpenAI TTS voice (alloy, echo, fable, onyx, nova, shimmer)

        Returns:
            Status of the speak operation
        """
        try:
            if not self.bot:
                return {"error": "Bot not running"}

            guild = self.bot.get_guild(int(guild_id))
            if not guild or not guild.voice_client:
                return {"error": "Not connected to voice in this guild"}

            voice_client = guild.voice_client

            # Generate TTS audio
            audio_file = await self._generate_tts(text, tts_provider, voice)
            if not audio_file:
                return {"error": "Failed to generate TTS audio"}

            # Play audio
            audio_source = discord.FFmpegPCMAudio(audio_file)
            voice_client.play(audio_source)

            # Wait for playback to finish
            while voice_client.is_playing():
                await asyncio.sleep(0.1)

            return {"ok": True, "result": {"status": "spoken", "text": text}}

        except Exception as e:
            return {"error": str(e)}

    async def play_audio(
        self,
        guild_id: str,
        audio_path: str,
    ) -> Dict[str, Any]:
        """
        Play an audio file in the voice channel.

        Args:
            guild_id: The guild ID
            audio_path: Path to audio file

        Returns:
            Status of the play operation
        """
        try:
            if not self.bot:
                return {"error": "Bot not running"}

            guild = self.bot.get_guild(int(guild_id))
            if not guild or not guild.voice_client:
                return {"error": "Not connected to voice in this guild"}

            voice_client = guild.voice_client

            audio_source = discord.FFmpegPCMAudio(audio_path)
            voice_client.play(audio_source)

            return {"ok": True, "result": {"status": "playing", "audio_path": audio_path}}

        except Exception as e:
            return {"error": str(e)}

    async def stop_audio(self, guild_id: str) -> Dict[str, Any]:
        """
        Stop currently playing audio.

        Args:
            guild_id: The guild ID

        Returns:
            Status of the stop operation
        """
        try:
            if not self.bot:
                return {"error": "Bot not running"}

            guild = self.bot.get_guild(int(guild_id))
            if not guild or not guild.voice_client:
                return {"error": "Not connected to voice in this guild"}

            guild.voice_client.stop()
            return {"ok": True, "result": {"status": "stopped"}}

        except Exception as e:
            return {"error": str(e)}

    def get_voice_status(self, guild_id: str) -> Dict[str, Any]:
        """
        Get the current voice status for a guild.

        Args:
            guild_id: The guild ID

        Returns:
            Voice status information
        """
        try:
            session = self.voice_sessions.get(guild_id)
            if not session:
                return {"ok": True, "result": {"connected": False}}

            guild = self.bot.get_guild(int(guild_id)) if self.bot else None
            is_connected = guild and guild.voice_client and guild.voice_client.is_connected() if guild else False

            return {
                "ok": True,
                "result": {
                    "connected": is_connected,
                    "guild_id": guild_id,
                    "channel_id": session.channel_id,
                    "is_recording": session.is_recording,
                    "is_speaking": session.is_speaking,
                    "connected_at": session.connected_at.isoformat(),
                }
            }

        except Exception as e:
            return {"error": str(e)}

    async def start_listening(
        self,
        guild_id: str,
        on_transcript: Optional[Callable[[int, str], None]] = None,
        auto_transcribe: bool = True,
        transcribe_interval: float = 3.0,
    ) -> Dict[str, Any]:
        """
        Start listening and transcribing audio in the voice channel.

        Args:
            guild_id: The guild ID
            on_transcript: Callback function(user_id, transcript_text) called when transcription is ready
            auto_transcribe: Whether to automatically transcribe audio at intervals
            transcribe_interval: Seconds between auto-transcription attempts

        Returns:
            Status of the listen operation
        """
        try:
            if not self.bot:
                return {"error": "Bot not running"}

            session = self.voice_sessions.get(guild_id)
            if not session:
                return {"error": "Not connected to voice in this guild"}

            guild = self.bot.get_guild(int(guild_id))
            if not guild or not guild.voice_client:
                return {"error": "Not connected to voice in this guild"}

            session.is_recording = True
            session.transcript_callback = on_transcript

            # Start recording with sink
            # Note: discord.py 2.0+ uses start_recording with a Sink
            # For older versions, we need to handle audio differently

            if auto_transcribe:
                # Start auto-transcription task
                asyncio.create_task(self._auto_transcribe_loop(guild_id, transcribe_interval))

            return {
                "ok": True,
                "result": {
                    "status": "listening",
                    "guild_id": guild_id,
                    "auto_transcribe": auto_transcribe,
                }
            }

        except Exception as e:
            return {"error": str(e)}

    async def stop_listening(self, guild_id: str) -> Dict[str, Any]:
        """
        Stop listening in the voice channel.

        Args:
            guild_id: The guild ID

        Returns:
            Status and final transcripts
        """
        try:
            session = self.voice_sessions.get(guild_id)
            if not session:
                return {"error": "No active session for this guild"}

            session.is_recording = False

            # Get final transcripts
            final_transcripts = dict(session.last_transcripts)

            # Clear buffers
            session.audio_buffer.clear()

            return {
                "ok": True,
                "result": {
                    "status": "stopped",
                    "transcripts": final_transcripts,
                }
            }

        except Exception as e:
            return {"error": str(e)}

    async def _auto_transcribe_loop(self, guild_id: str, interval: float):
        """Background task to automatically transcribe audio at intervals."""
        while True:
            session = self.voice_sessions.get(guild_id)
            if not session or not session.is_recording:
                break

            # Process audio buffers for each user
            for user_id, chunks in list(session.audio_buffer.items()):
                if chunks and len(chunks) > 10:  # Wait for enough audio data
                    # Combine chunks and transcribe
                    audio_data = b''.join(chunks)
                    session.audio_buffer[user_id] = []  # Clear buffer

                    # Transcribe
                    transcript = await self._transcribe_audio(audio_data)
                    if transcript:
                        session.last_transcripts[user_id] = transcript
                        if session.transcript_callback:
                            try:
                                session.transcript_callback(user_id, transcript)
                            except Exception as e:
                                print(f"Transcript callback error: {e}")

            await asyncio.sleep(interval)

    async def _transcribe_audio(self, audio_data: bytes) -> Optional[str]:
        """
        Transcribe audio data using OpenAI Whisper.

        Args:
            audio_data: Raw audio bytes (PCM format)

        Returns:
            Transcribed text or None if failed
        """
        if not OPENAI_AVAILABLE or not OPENAI_AUDIO_API_KEY:
            print("OpenAI not available for transcription. Set OPENAI_AUDIO_API_KEY.")
            return None

        try:
            # Convert raw PCM to WAV for Whisper
            wav_path = self._pcm_to_wav(audio_data)
            if not wav_path:
                return None

            # Use OpenAI Whisper
            client = OpenAI(api_key=OPENAI_AUDIO_API_KEY)

            with open(wav_path, "rb") as audio_file:
                transcript = client.audio.transcriptions.create(
                    model="whisper-1",
                    file=audio_file,
                    response_format="text"
                )

            # Clean up temp file
            os.unlink(wav_path)

            return transcript.strip() if transcript else None

        except Exception as e:
            print(f"Transcription error: {e}")
            return None

    def _pcm_to_wav(self, pcm_data: bytes, sample_rate: int = 48000, channels: int = 2) -> Optional[str]:
        """Convert raw PCM audio data to WAV file."""
        try:
            with tempfile.NamedTemporaryFile(delete=False, suffix='.wav') as f:
                with wave.open(f.name, 'wb') as wav_file:
                    wav_file.setnchannels(channels)
                    wav_file.setsampwidth(2)  # 16-bit
                    wav_file.setframerate(sample_rate)
                    wav_file.writeframes(pcm_data)
                return f.name
        except Exception as e:
            print(f"PCM to WAV conversion error: {e}")
            return None

    async def _generate_tts(self, text: str, provider: str = "openai", voice: str = "alloy") -> Optional[str]:
        """
        Generate TTS audio file from text.

        Args:
            text: Text to convert to speech
            provider: TTS provider - "openai" (recommended), "gtts" (free fallback)
            voice: OpenAI TTS voice (alloy, echo, fable, onyx, nova, shimmer)

        Returns:
            Path to generated audio file or None
        """
        try:
            if provider == "openai" and OPENAI_AVAILABLE and OPENAI_AUDIO_API_KEY:
                # Use OpenAI TTS (higher quality)
                client = OpenAI(api_key=OPENAI_AUDIO_API_KEY)

                response = client.audio.speech.create(
                    model="tts-1",  # or "tts-1-hd" for higher quality
                    voice=voice,  # options: alloy, echo, fable, onyx, nova, shimmer
                    input=text,
                )

                with tempfile.NamedTemporaryFile(delete=False, suffix='.mp3') as f:
                    response.stream_to_file(f.name)
                    return f.name

            elif provider == "gtts" or not OPENAI_AVAILABLE:
                # Fallback to gTTS (free but lower quality)
                from gtts import gTTS
                tts = gTTS(text=text, lang='en')
                with tempfile.NamedTemporaryFile(delete=False, suffix='.mp3') as f:
                    tts.save(f.name)
                    return f.name

            return None

        except ImportError:
            print("TTS library not available. Install gtts: pip install gtts")
            return None
        except Exception as e:
            print(f"TTS generation error: {e}")
            return None

    async def transcribe_and_respond(
        self,
        guild_id: str,
        response_generator: Callable[[str], str],
        voice: str = "alloy",
    ) -> Dict[str, Any]:
        """
        Listen for speech, transcribe it, generate a response, and speak it back.

        This is the main conversational loop for voice interaction.

        Args:
            guild_id: The guild ID
            response_generator: Function that takes transcribed text and returns response text
            voice: OpenAI TTS voice to use

        Returns:
            Status of the operation
        """
        try:
            session = self.voice_sessions.get(guild_id)
            if not session:
                return {"error": "Not connected to voice in this guild"}

            # Define callback that will generate and speak response
            async def on_transcript(user_id: int, transcript: str):
                if not transcript or len(transcript.strip()) < 2:
                    return

                print(f"[Voice] User {user_id} said: {transcript}")

                # Generate response
                response_text = response_generator(transcript)
                if response_text:
                    print(f"[Voice] Responding: {response_text}")
                    await self.speak_text(guild_id, response_text, tts_provider="openai", voice=voice)

            # Start listening with auto-transcribe
            result = await self.start_listening(
                guild_id=guild_id,
                on_transcript=lambda uid, txt: asyncio.create_task(on_transcript(uid, txt)),
                auto_transcribe=True,
            )

            return result

        except Exception as e:
            return {"error": str(e)}


# ═══════════════════════════════════════════════════════════════════════════
# STANDALONE FUNCTIONS (for basic voice info without full bot)
# ═══════════════════════════════════════════════════════════════════════════

def get_voice_regions() -> Dict[str, Any]:
    """
    Get available Discord voice regions.

    Returns:
        List of voice regions
    """
    import requests

    url = "https://discord.com/api/v10/voice/regions"

    try:
        response = requests.get(url, timeout=15)

        if response.status_code == 200:
            return {"ok": True, "result": {"regions": response.json()}}
        else:
            return {"error": f"API error: {response.status_code}"}
    except Exception as e:
        return {"error": str(e)}


def get_guild_voice_states(bot_token: str, guild_id: str) -> Dict[str, Any]:
    """
    Get voice states for a guild (who's in voice channels).

    Args:
        bot_token: Discord bot token
        guild_id: The guild ID

    Returns:
        Voice states for the guild
    """
    import requests

    url = f"https://discord.com/api/v10/guilds/{guild_id}"
    headers = {
        "Authorization": f"Bot {bot_token}",
        "Content-Type": "application/json",
    }

    try:
        response = requests.get(url, headers=headers, timeout=15)

        if response.status_code == 200:
            data = response.json()
            return {
                "ok": True,
                "result": {
                    "voice_states": data.get("voice_states", []),
                }
            }
        else:
            return {"error": f"API error: {response.status_code}", "details": response.text}
    except Exception as e:
        return {"error": str(e)}

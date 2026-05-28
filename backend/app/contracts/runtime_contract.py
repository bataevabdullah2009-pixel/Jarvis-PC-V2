from __future__ import annotations

from typing import Any
from pydantic import BaseModel, Field


class ListenerStatus(BaseModel):
    status: str = Field(..., description="Active status: idle, listening, speaking, blocked, error")
    device_id: str = Field(..., description="ID of the active audio input device")
    device_name: str = Field("", description="Name of the active audio input device")
    wake_words: list[str] = Field(default_factory=list, description="List of wake words")
    is_listening: bool = Field(False, description="Is listener currently running and capturing audio")
    error_message: str | None = Field(None, description="Detailed error message if state is error or blocked")
    fixes: list[str] = Field(default_factory=list, description="Recommended steps to fix current issues")


class AIProviderStatus(BaseModel):
    provider: str = Field(..., description="Primary provider name: groq, openrouter, local")
    model: str = Field(..., description="Active model name")
    configured: bool = Field(False, description="Is API key configured properly")
    latency_ms: int | None = Field(None, description="Last recorded planner latency in milliseconds")
    available: bool = Field(True, description="Is provider currently reachable")


class VoiceProviderStatus(BaseModel):
    provider: str = Field(..., description="Active TTS provider: fish_audio, piper_local, pyttsx3")
    voice_id: str | None = Field(None, description="Active voice ID or model tag")
    configured: bool = Field(False, description="Is provider fully configured and authorized")
    voice_tone: str = Field("calm", description="Configured speaking tone: calm, serious, fast, cinematic, friendly")


class TTSStatus(BaseModel):
    status: str = Field(..., description="TTS system status: ready, speaking, error")
    queue_size: int = Field(0, description="Number of items waiting in TTS queue")
    active: bool = Field(False, description="Is TTS actively playing sound right now")


class RuntimeStatus(BaseModel):
    app_name: str = Field("JARVIS PC V2", description="Application name")
    version: str = Field("0.1.0", description="Application version")
    phase: str = Field("phase-2-3-1", description="Current development phase contract")
    debug_mode: bool = Field(False, description="Debug mode state")
    listener: ListenerStatus = Field(..., description="Voice listener system status")
    ai: AIProviderStatus = Field(..., description="AI planner service status")
    voice: VoiceProviderStatus = Field(..., description="Voice output settings")
    tts: TTSStatus = Field(..., description="Active text-to-speech status")


class SettingsData(BaseModel):
    assistant_name: str = Field("Джарвис", description="Name of assistant used in wake filters")
    assistant_display_name: str = Field("JARVIS", description="Display label in HUD UI")
    assistant_address_style: str = Field("сэр", description="Address mode: сэр, мем, без обращения")
    voice_wake_enabled: bool = Field(True, description="Enable voice activation")
    clap_enabled: bool = Field(True, description="Enable clap trigger")
    autostart_enabled: bool = Field(False, description="Launch voice engines automatically")
    voice_volume: int = Field(70, description="System speech volume from 0 to 100")
    ai_primary: str = Field("groq", description="Primary AI brain")
    ai_fallback: str = Field("openrouter", description="Secondary fallback brain")
    tts_primary: str = Field("fish_audio", description="Primary voice synthesis")
    cooldown_ms: int = Field(2500, description="Post-TTS cooldown in ms to prevent self-looping")
    listener_device_id: str = Field("default", description="Capture audio device identifier")
    wake_words: list[str] = Field(default_factory=list, description="Comma-separated wake words")


class CommandData(BaseModel):
    id: str = Field(..., description="Unique command string identifier")
    name: str = Field(..., description="Friendly name of the action")
    phrases: list[str] = Field(..., description="List of phrases that trigger this action")
    action_type: str = Field(..., description="Type of action: file, url, scenario, keypress, shell")
    action_target: str = Field(..., description="Target script path, url, or hotkey code")
    enabled: bool = Field(True, description="State of the command toggle")


class AssistantResult(BaseModel):
    query: str = Field(..., description="Original text captured from speech or chat input")
    response: str = Field(..., description="Text result produced by the AI brain")
    command_triggered: str | None = Field(None, description="Command ID triggered if matching rules")
    success: bool = Field(True, description="True if no pipeline or critical runtime faults occurred")
    latency: dict[str, int] = Field(
        default_factory=dict,
        description="High-resolution latency breakdown in ms: router_ms, ai_ms, tts_ms, total_ms"
    )

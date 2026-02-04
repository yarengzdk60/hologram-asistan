import os
import time
import math
import wave
import asyncio
import logging
import requests
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor
import pyaudio
import speech_recognition as sr
from dotenv import load_dotenv
from elevenlabs.client import ElevenLabs
from elevenlabs import VoiceSettings
import re

from server.components.websocket import broadcast_speak, broadcast_state, broadcast_error, broadcast_message
from server.core.word_filter import WordFilter

load_dotenv()  # Fallback, though main.py handles it
logger = logging.getLogger("VoiceController")


class VoiceController:
    """
    Handles the voice interaction pipeline: STT -> Gemini -> ElevenLabs TTS.
    Hands-free mode: Continuously listens and responds in a loop.
    Enforces a childlike, friendly persona.
    """
    CHUNK = 1024
    FORMAT = pyaudio.paInt16
    CHANNELS = 1
    RATE = 16000

    SILENCE_THRESHOLD = 300
    MIN_ENERGY_THRESHOLD = 500
    SILENCE_DURATION = 2.0

    # ElevenLabs Personality Settings
    VOICE_ID = "MF3mGyEYCl7XYW7LecBy" # "Elli" (child-like)
    EL_MODEL = "eleven_multilingual_v2"
    VOICE_SETTINGS = VoiceSettings(
        stability=0.25,
        similarity_boost=0.75,
        style=0.6,
        use_speaker_boost=True
    )

    def __init__(self, task_manager, audio_dir=None):
        self.tm = task_manager
        self.audio_dir = audio_dir or Path(".audio_cache")
        self.audio_dir.mkdir(exist_ok=True)
        self.audio = None
        self.recognizer = sr.Recognizer()
        self._executor = ThreadPoolExecutor(max_workers=5)
        
        # Word Filtering
        self.word_filter = WordFilter()
        
        # Hands-free state
        self.is_first_interaction = True
        self.is_running = False

        # API Keys
        self.api_key = os.getenv("GOOGLE_API_KEY", "").strip()
        self.gemini_model = os.getenv("GEMINI_MODEL", "gemini-1.5-flash").strip()
        self.el_api_key = os.getenv("ELEVENLABS_API_KEY", "").strip()

        if self.api_key:
            masked_key = self.api_key[:4] + "..." + self.api_key[-4:]
            logger.info(f"Gemini API Initialized with key: {masked_key} and model: {self.gemini_model}")
        else:
            logger.error("GOOGLE_API_KEY NOT FOUND IN ENVIRONMENT!")

        # Initialize ElevenLabs
        if self.el_api_key:
            try:
                self.el_client = ElevenLabs(api_key=self.el_api_key)
                logger.info(f"ElevenLabs TTS initialized with voice: {self.VOICE_ID}")
            except Exception as e:
                logger.error(f"ElevenLabs initialization failed: {e}")
                self.el_client = None
        else:
            logger.error("ELEVENLABS_API_KEY NOT FOUND IN ENVIRONMENT!")
            self.el_client = None

        try:
            self.audio = pyaudio.PyAudio()
        except Exception as e:
            logger.error(f"PyAudio initialization failed: {e}")

    async def start(self, payload=None):
        """Starts the voice pipeline via TaskManager."""
        self.is_first_interaction = True # Reset on start
        await self.tm.start("voice_pipeline", self.run_pipeline_loop())

    async def stop(self, payload=None):
        """Stops the voice pipeline via TaskManager."""
        self.is_running = False
        await self.tm.cancel("voice_pipeline")

    async def _run_in_executor(self, func, *args):
        try:
            loop = asyncio.get_running_loop()
            return await loop.run_in_executor(self._executor, func, *args)
        except asyncio.CancelledError:
            logger.info("Executor task cancelled.")
            raise

    def _record_sync(self):
        """Blocking microphone recording with silence detection and timeouts."""
        if not self.audio or not self.is_running:
            return None
        stream = None
        try:
            stream = self.audio.open(format=self.FORMAT, channels=self.CHANNELS,
                                     rate=self.RATE, input=True, frames_per_buffer=self.CHUNK)
            frames = []
            started = False
            silent_chunks = 0
            max_silent = int(self.SILENCE_DURATION * self.RATE / self.CHUNK)

            # 10 seconds to start speaking
            max_initial_wait = int(10.0 * self.RATE / self.CHUNK)
            # 20 seconds total max
            max_total_duration = int(20.0 * self.RATE / self.CHUNK)

            ticks = 0
            logger.info("🎤 Microphone listening...")

            while ticks < max_total_duration and self.is_running:
                ticks += 1
                try:
                    data = stream.read(self.CHUNK, exception_on_overflow=False)
                except Exception as e:
                    logger.error(f"Stream read error: {e}")
                    break

                audio_data = [int.from_bytes(
                    data[i:i+2], 'little', signed=True) for i in range(0, len(data), 2)]
                rms = math.sqrt(sum(x*x for x in audio_data) /
                                len(audio_data)) if audio_data else 0

                if not started:
                    if rms > self.MIN_ENERGY_THRESHOLD:
                        started = True
                        logger.info("🗣️ Speech started")
                    elif ticks > max_initial_wait:
                        return None

                if started:
                    frames.append(data)
                    if rms < self.SILENCE_THRESHOLD:
                        silent_chunks += 1
                    else:
                        silent_chunks = 0

                    if silent_chunks > max_silent:
                        logger.info("🤫 Silence detected, stopping recording")
                        break

            if len(frames) < 10:
                return None

            path = self.audio_dir / f"rec_{int(time.time())}.wav"
            wf = wave.open(str(path), 'wb')
            wf.setnchannels(self.CHANNELS)
            wf.setsampwidth(self.audio.get_sample_size(self.FORMAT))
            wf.setframerate(self.RATE)
            wf.writeframes(b''.join(frames))
            wf.close()
            return path
        except Exception as e:
            logger.error(f"Recording error: {e}")
            return None
        finally:
            if stream:
                try:
                    stream.stop_stream()
                    stream.close()
                except:
                    pass

    def _stt_sync(self, path):
        try:
            with sr.AudioFile(str(path)) as source:
                audio = self.recognizer.record(source)
            return self.recognizer.recognize_google(audio, language='tr-TR')
        except Exception as e:
            logger.warning(f"STT Error: {e}")
            return None

    def _gemini_sync(self, prompt):
        url = f"https://generativelanguage.googleapis.com/v1/models/{self.gemini_model}:generateContent?key={self.api_key}"
        
        # System instructions for personality
        system_instruction = (
            "Sen bir hologram asistansın. "
            "Karakterin: Çocuksu, nazik, arkadaş canlısı, sakin ve sıcak. "
            "Konuşma tarzın: Kısa cümleler kur, hafif oyunbaz ol ama asla cıvıklaşma. "
            "Robotik tondan kaçın, insansı ve samimi ol. "
            "Cevapların kısa ve öz olsun. "
        )
        
        body = {"contents": [
            {"parts": [{"text": f"{system_instruction}\n\nKullanıcı: {prompt}"}]}]}
        try:
            resp = requests.post(url, json=body, timeout=10)
            if resp.status_code == 200:
                return resp.json()['candidates'][0]['content']['parts'][0]['text']
            logger.error(f"Gemini API Error {resp.status_code}: {resp.text}")
            return "Hata oluştu, tekrar deneyebilir misin?"
        except Exception as e:
            logger.error(f"Gemini Request failed: {e}")
            return "Bağlantı hatası."

    def _tts_sync(self, text):
        if not self.el_client:
            logger.warning("Falling back to gTTS (ElevenLabs client not initialized)")
            return self._gtts_fallback(text)
            
        try:
            logger.info(f"Generating ElevenLabs audio for: '{text[:30]}...'")
            audio_generator = self.el_client.text_to_speech.convert(
                text=text,
                voice_id=self.VOICE_ID,
                model_id=self.EL_MODEL,
                voice_settings=self.VOICE_SETTINGS
            )
            
            # Combine generator bytes
            audio_bytes = b"".join(audio_generator)
            
            path = self.audio_dir / f"el_{int(time.time())}.mp3"
            with open(path, "wb") as f:
                f.write(audio_bytes)
                
            return path
        except Exception as e:
            logger.error(f"ElevenLabs TTS Error: {e}")
            return self._gtts_fallback(text)

    def _gtts_fallback(self, text):
        from gtts import gTTS
        try:
            path = self.audio_dir / f"fb_{int(time.time())}.mp3"
            tts = gTTS(text=text, lang='tr')
            tts.save(str(path))
            return path
        except Exception as e:
            logger.error(f"gTTS Fallback Error: {e}")
            return None

    async def run_pipeline_loop(self):
        """
        The main voice loop task for hands-free mode.
        """
        self.is_running = True
        logger.info("🚀 Hands-free Voice Pipeline Started")
        
        try:
            while self.is_running:
                await broadcast_state("LISTENING")
                
                path = await self._run_in_executor(self._record_sync)
                
                if not self.is_running:
                    break
                    
                if not path:
                    await asyncio.sleep(0.5)
                    continue

                await broadcast_state("WAITING")

                text = await self._run_in_executor(self._stt_sync, path)
                if text:
                    logger.info(f"User: {text}")
                    await broadcast_message({"type": "transcribe", "text": text})
                    
                    # Greeting Logic
                    if self.is_first_interaction:
                        response = "Merhaba! Ben buradayım!"
                        self.is_first_interaction = False
                        logger.info("👋 First interaction: Greeted user")
                    else:
                        # Profanity filter: if user message contains banned words, reply with the default polite message
                        if self.word_filter.contains_profanity(text):
                            response = "Lütfen saygı kurallarına uy."
                            logger.info("🔒 Profanity detected in user input; sending filtered response")
                        else:
                            ai_response = await self._run_in_executor(self._gemini_sync, text)
                            # Also filter the AI response just in case
                            response = self.word_filter.censor_text(ai_response)
                            if response != ai_response:
                                logger.info("🔒 AI response was censored")
                            logger.info(f"AI: {response}")

                    audio_path = await self._run_in_executor(self._tts_sync, response)
                    if audio_path:
                        url = f"http://localhost:8090/audio/{audio_path.name}"
                        await broadcast_speak(url, 15.0, response)
                        
                        # Wait for speaking to end (estimated)
                        words = len(response.split())
                        wait_time = (words * 0.6) + 3.0 # ElevenLabs is slightly slower/more expressive
                        logger.info(f"🔈 Speaking... Waiting {wait_time:.1f}s")
                        await asyncio.sleep(wait_time)
                
                await broadcast_state("IDLE")
                await asyncio.sleep(0.5)

        except asyncio.CancelledError:
            logger.info("Voice pipeline cancelled.")
        except Exception as e:
            logger.error(f"Error in voice loop: {e}")
            await broadcast_error(str(e))
        finally:
            self.is_running = False
            await broadcast_state("IDLE")

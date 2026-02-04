"""
Voice Component - Voice recognition and AI response
Optimized for async operation and better performance
"""
import pyaudio
import wave
import time
import asyncio
import os
import math
import requests
from pathlib import Path
from enum import Enum
import speech_recognition as sr
from gtts import gTTS
from concurrent.futures import ThreadPoolExecutor

from server.components.websocket import broadcast_speak


class VoiceState(Enum):
    """Explicit state machine for voice component"""
    IDLE = "idle"
    LISTENING = "listening"
    RECORDING = "recording"
    PROCESSING = "processing"


class VoiceComponent:
    """Voice recognition and AI response component"""
    
    def __init__(self):
        # Audio settings
        self.CHUNK = 1024
        self.FORMAT = pyaudio.paInt16
        self.CHANNELS = 1
        self.RATE = 16000
        
        # Silence detection
        self.SILENCE_THRESHOLD = 500  # RMS threshold
        self.MIN_ENERGY_THRESHOLD = 300  # Minimum energy to start recording
        self.SILENCE_DURATION = 1.5  # seconds of silence to stop recording
        self.MIN_RECORDING_DURATION = 0.5  # minimum recording duration
        
        # File paths
        self.audio_dir = Path("audio_output")
        self.audio_dir.mkdir(exist_ok=True)
        
        # Audio objects
        self.audio = None
        self.recognizer = sr.Recognizer()
        
        # State - CRITICAL: flags prevent concurrent access
        self.running = False
        self.active = False
        self.is_recording = False  # PyAudio safety flag
        self.is_loop_running = False  # Voice loop safety flag
        self.state = VoiceState.IDLE  # Explicit state machine
        self._executor = ThreadPoolExecutor(max_workers=3, thread_name_prefix="voice")
        
        # HuggingFace API configuration
        self.hf_api_key = os.getenv("HUGGINGFACE_API_KEY", "")
        if self.hf_api_key:
            self.hf_api_url = "https://api-inference.huggingface.co/models/microsoft/DialoGPT-medium"
            print("[OK] HuggingFace API key loaded")
        else:
            self.hf_api_key = None
            self.hf_api_url = None
            print("[WARN] HuggingFace API key not set - AI responses will be limited")
        
        # Initialize PyAudio lazily
        try:
            self.audio = pyaudio.PyAudio()
        except Exception as e:
            print(f"⚠️ PyAudio initialization error: {e}")
            self.audio = None
    
    def is_silent(self, audio_data):
        """Check if audio chunk is silent"""
        if not audio_data:
            return True
        rms = math.sqrt(sum(x * x for x in audio_data) / len(audio_data))
        return rms < self.SILENCE_THRESHOLD
    
    def _record_audio_sync(self):
        """Record audio until silence is detected (synchronous, runs in executor)"""
        # SAFETY: Prevent concurrent recording
        if self.is_recording:
            print("⚠️ Already recording - skipping")
            return None
            
        if not self.active or not self.running:
            return None
        
        if not self.audio:
            print("❌ PyAudio not initialized")
            return None
            
        self.is_recording = True
        stream = None
        
        try:
            stream = self.audio.open(
                format=self.FORMAT,
                channels=self.CHANNELS,
                rate=self.RATE,
                input=True,
                frames_per_buffer=self.CHUNK
            )
        except Exception as e:
            print(f"❌ Failed to open audio stream: {e}")
            self.is_recording = False
            return None
        
        frames = []
        silent_chunks = 0
        silent_chunks_threshold = int(self.SILENCE_DURATION * self.RATE / self.CHUNK)
        started = False
        start_time = time.time()
        max_energy = 0
        
        print("🎤 Listening...")
        
        try:
            while self.running and self.active and self.is_recording:
                try:
                    data = stream.read(self.CHUNK, exception_on_overflow=False)
                    audio_data = list(int.from_bytes(data[i:i+2], byteorder='little', signed=True) 
                                     for i in range(0, len(data), 2))
                    
                    silent = self.is_silent(audio_data)
                    
                    # Calculate energy
                    if audio_data:
                        rms = math.sqrt(sum(x * x for x in audio_data) / len(audio_data))
                        max_energy = max(max_energy, rms)
                    else:
                        rms = 0
                    
                    # ENERGY FILTER: Only start recording if energy exceeds threshold
                    if not started and rms > self.MIN_ENERGY_THRESHOLD:
                        started = True
                        print(f"🎤 Speech detected (energy: {rms:.0f})")
                    
                    if not silent and started:
                        silent_chunks = 0
                        frames.append(data)
                    elif started:
                        silent_chunks += 1
                        frames.append(data)
                        
                        if silent_chunks >= silent_chunks_threshold:
                            # Check minimum duration
                            if time.time() - start_time >= self.MIN_RECORDING_DURATION:
                                break
                    else:
                        # Waiting for speech to start
                        start_time = time.time()
                except Exception as e:
                    print(f"⚠️ Audio read error: {e}")
                    break
        
        finally:
            self.is_recording = False
            if stream:
                try:
                    stream.stop_stream()
                    stream.close()
                except:
                    pass
        
        # ENERGY FILTER: Reject recording if max energy too low
        if max_energy < self.MIN_ENERGY_THRESHOLD:
            print(f"⚠️ Recording rejected - too quiet (max energy: {max_energy:.0f})")
            return None
        
        if not frames:
            return None
        
        # Save to WAV file
        try:
            timestamp = int(time.time())
            wav_path = self.audio_dir / f"recording_{timestamp}.wav"
            
            wf = wave.open(str(wav_path), 'wb')
            wf.setnchannels(self.CHANNELS)
            wf.setsampwidth(self.audio.get_sample_size(self.FORMAT))
            wf.setframerate(self.RATE)
            wf.writeframes(b''.join(frames))
            wf.close()
            
            print(f"💾 Audio saved: {wav_path}")
            return wav_path
        except Exception as e:
            print(f"❌ Failed to save audio: {e}")
            return None
    
    async def record_audio(self):
        """Record audio until silence is detected (async wrapper)"""
        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(self._executor, self._record_audio_sync)
    
    def _speech_to_text_sync(self, audio_path):
        """Convert speech to text using Google Speech Recognition (synchronous)"""
        try:
            with sr.AudioFile(str(audio_path)) as source:
                audio = self.recognizer.record(source)
            
            text = self.recognizer.recognize_google(audio, language='tr-TR')
            print(f"📝 Transcribed: {text}")
            return text
        except sr.UnknownValueError:
            print("❌ Could not understand audio")
            return None
        except sr.RequestError as e:
            print(f"❌ Speech recognition error: {e}")
            return None
        except Exception as e:
            print(f"❌ Speech recognition exception: {e}")
            return None
    
    async def speech_to_text(self, audio_path):
        """Convert speech to text using Google Speech Recognition (async wrapper)"""
        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(self._executor, self._speech_to_text_sync, audio_path)
    
    def _ask_ai_sync(self, question):
        """Ask question to AI and get response using HuggingFace (synchronous)"""
        if not self.hf_api_key:
            print("[AI] ⚠️ HuggingFace API key not set")
            return "Üzgünüm, AI API anahtarı ayarlanmamış."
        
        print(f"[AI] 🚀 Sending request to HuggingFace API")
        print(f"[AI] 📝 Question: '{question}'")
        
        try:
            headers = {
                "Authorization": f"Bearer {self.hf_api_key}",
                "Content-Type": "application/json"
            }
            
            payload = {
                "inputs": question,
                "parameters": {
                    "max_length": 150,
                    "temperature": 0.7,
                    "top_p": 0.9,
                    "do_sample": True
                }
            }
            
            print(f"[AI] 🌐 Making HTTP POST to {self.hf_api_url}")
            response = requests.post(
                self.hf_api_url,
                headers=headers,
                json=payload,
                timeout=30
            )
            
            print(f"[AI] 📡 Response status: {response.status_code}")
            
            if response.status_code == 200:
                result = response.json()
                print(f"[AI] 📦 Raw response: {result}")
                
                # HuggingFace returns list of dicts with 'generated_text'
                if isinstance(result, list) and len(result) > 0:
                    if 'generated_text' in result[0]:
                        answer = result[0]['generated_text'].strip()
                    elif 'text' in result[0]:
                        answer = result[0]['text'].strip()
                    else:
                        # Fallback: use first value
                        answer = str(result[0]).strip()
                else:
                    answer = str(result).strip()
                
                # Clean up response
                if not answer or len(answer) < 3:
                    print(f"[AI] ⚠️ Response too short: '{answer}'")
                    return "Üzgünüm, cevap oluşturamadım."
                
                print(f"[AI] ✅ Response: '{answer}'")
                return answer
                
            elif response.status_code == 503:
                print(f"[AI] ⚠️ Model loading (503), retrying...")
                # Model is loading, wait and retry once
                time.sleep(5)
                response = requests.post(self.hf_api_url, headers=headers, json=payload, timeout=30)
                if response.status_code == 200:
                    result = response.json()
                    if isinstance(result, list) and len(result) > 0:
                        answer = result[0].get('generated_text', '').strip()
                        if answer:
                            print(f"[AI] ✅ Response after retry: '{answer}'")
                            return answer
                
                print(f"[AI] ❌ Model still loading after retry")
                return "Üzgünüm, AI modeli yükleniyor. Lütfen tekrar deneyin."
                
            else:
                print(f"[AI] ❌ API error: {response.status_code}")
                print(f"[AI] ❌ Response body: {response.text}")
                
                # Send error to frontend
                from server.components.websocket import broadcast_error
                try:
                    loop = asyncio.get_event_loop()
                    asyncio.run_coroutine_threadsafe(
                        broadcast_error(f"AI API hatası: {response.status_code}"),
                        loop
                    )
                except:
                    pass
                
                return "Üzgünüm, AI servisi şu an yanıt veremiyor."
                
        except requests.exceptions.Timeout:
            print(f"[AI] ❌ Request timeout")
            return "Üzgünüm, AI yanıt vermedi (timeout)."
        except requests.exceptions.RequestException as e:
            print(f"[AI] ❌ Request error: {e}")
            return "Üzgünüm, AI bağlantı hatası."
        except Exception as e:
            print(f"[AI] ❌ Unexpected error: {e}")
            import traceback
            traceback.print_exc()
            return "Üzgünüm, bir hata oluştu."
    
    async def ask_ai(self, question):
        """Ask question to AI and get response (async wrapper)"""
        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(self._executor, self._ask_ai_sync, question)
    
    def _text_to_speech_sync(self, text, lang='tr'):
        """Convert text to speech and save as MP3 (synchronous)"""
        try:
            tts = gTTS(text=text, lang=lang, slow=False)
            timestamp = int(time.time())
            mp3_path = self.audio_dir / f"response_{timestamp}.mp3"
            tts.save(str(mp3_path))
            
            # Get duration (approximate: ~150 words per minute)
            word_count = len(text.split())
            duration = (word_count / 150) * 60  # seconds
            
            print(f"🔊 TTS saved: {mp3_path} (duration: {duration:.1f}s)")
            return mp3_path, duration
        except Exception as e:
            print(f"❌ TTS error: {e}")
            return None, 0
    
    async def text_to_speech(self, text, lang='tr'):
        """Convert text to speech and save as MP3 (async wrapper)"""
        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(self._executor, self._text_to_speech_sync, text, lang)
    
    async def process_voice_async(self):
        """Main voice processing loop (fully async)"""
        # LOOP GUARD: Prevent multiple concurrent loops
        if self.is_loop_running:
            print("⚠️ Voice loop already running - ignoring")
            return
        
        self.is_loop_running = True
        print("🎤 Voice component async loop started")
        
        try:
            while self.running:
                if not self.active:
                    self.state = VoiceState.IDLE
                    await asyncio.sleep(0.1)
                    continue
                
                try:
                    # STATE: LISTENING
                    self.state = VoiceState.LISTENING
                    print(f"[STATE] {self.state.value}")
                    
                    # Record audio (async)
                    self.state = VoiceState.RECORDING
                    print(f"[STATE] {self.state.value}")
                    audio_path = await self.record_audio()
                    if not audio_path:
                        self.state = VoiceState.IDLE
                        await asyncio.sleep(0.1)
                        continue
                    
                    # STATE: PROCESSING
                    self.state = VoiceState.PROCESSING
                    print(f"[STATE] {self.state.value} - Starting STT")
                    
                    # Speech to text (async)
                    text = await self.speech_to_text(audio_path)
                    if not text:
                        print("[STT] No text recognized")
                        self.state = VoiceState.IDLE
                        await asyncio.sleep(0.1)
                        continue
                    
                    print(f"[STT] ✅ Recognized: '{text}'")
                    
                    # Ask AI (async)
                    print(f"[AI] Calling HuggingFace with question: '{text}'")

                    response = await self.ask_ai(text)
                    print(f"[AI] ✅ Response received: '{response[:50]}...' (length: {len(response)})")
                    
                    # VALIDATION: Only proceed with TTS if we have a valid response
                    
                    if not response:
                     response = "Seni duyuyorum ama şu an cevap oluşturamıyorum."
                    # Text to speech (async)
                    print(f"[TTS] Generating speech for: '{response[:50]}...'")
                    mp3_path, duration = await self.text_to_speech(response)
                    if not mp3_path:
                        print("[TTS] ⚠️ Failed to generate audio")
                        self.state = VoiceState.IDLE
                        await asyncio.sleep(0.1)
                        continue
                    
                    print(f"[TTS] ✅ Generated: {mp3_path} (duration: {duration:.1f}s)")
                    
                    # Broadcast to clients - use HTTP URL for audio file
                    filename = mp3_path.name
                    audio_url = f"http://localhost:8090/audio/{filename}"
                    print(f"[BROADCAST] Sending audio URL to clients: {audio_url}")
                    await broadcast_speak(audio_url, duration)
                    print("[BROADCAST] ✅ Audio URL sent to clients")
                    
                    # Cleanup old audio files (keep last 5) - non-blocking
                    asyncio.create_task(self._cleanup_old_files_async())
                    
                    # Back to IDLE
                    self.state = VoiceState.IDLE
                    
                except Exception as e:
                    print(f"❌ Voice processing error: {e}")
                    import traceback
                    traceback.print_exc()
                    self.state = VoiceState.IDLE
                    await asyncio.sleep(0.5)
        finally:
            self.is_loop_running = False
            print("🎤 Voice loop stopped")
    
    async def _cleanup_old_files_async(self, keep=5):
        """Clean up old audio files asynchronously"""
        loop = asyncio.get_event_loop()
        await loop.run_in_executor(self._executor, self._cleanup_old_files_sync, keep)
    
    def _cleanup_old_files_sync(self, keep=5):
        """Clean up old audio files, keep only the most recent ones (synchronous)"""
        try:
            wav_files = sorted(self.audio_dir.glob("*.wav"), key=os.path.getmtime, reverse=True)
            mp3_files = sorted(self.audio_dir.glob("*.mp3"), key=os.path.getmtime, reverse=True)
            
            for old_file in wav_files[keep:]:
                try:
                    old_file.unlink()
                except:
                    pass
            for old_file in mp3_files[keep:]:
                try:
                    old_file.unlink()
                except:
                    pass
        except Exception as e:
            print(f"⚠️ Cleanup error: {e}")
    
    def start(self, loop: asyncio.AbstractEventLoop):
        """Start the voice component"""
        if self.running:
            print("⚠️ Voice component already running")
            return
        self.running = True
        asyncio.create_task(self.process_voice_async())
        print("🎤 Voice component started (async)")
    
    def stop(self):
        """Stop the voice component"""
        self.running = False
        self.active = False
        self.is_recording = False  # Force stop any recording
        
        if self.audio:
            try:
                self.audio.terminate()
                self.audio = None
            except:
                pass
        
        if self._executor:
            try:
                self._executor.shutdown(wait=False)
            except:
                pass
        print("🎤 Voice component stopped")
    
    def set_active(self, active: bool):
        """Set voice component active/inactive"""
        # ACTIVATION GUARD: Prevent redundant calls
        if self.active == active:
            print(f"⚠️ Voice already {'active' if active else 'inactive'} - ignoring")
            return
        
        self.active = active
        if active:
            print("🎤 Voice component activated")
        else:
            print("🎤 Voice component deactivated")

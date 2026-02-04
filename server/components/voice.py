import os
import time
import math
import wave
import asyncio
import requests
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor
import pyaudio
import speech_recognition as sr
from gtts import gTTS
from dotenv import load_dotenv

from server.components.websocket import broadcast_speak, broadcast_error, broadcast_state

load_dotenv()

class VoiceComponent:
    CHUNK = 1024
    FORMAT = pyaudio.paInt16
    CHANNELS = 1
    RATE = 16000
    
    # Silence Detection
    SILENCE_THRESHOLD = 500
    MIN_ENERGY_THRESHOLD = 800
    SILENCE_DURATION = 2.0
    MIN_RECORDING_DURATION = 0.5

    def __init__(self):
        self.audio_dir = Path("audio_output")
        self.audio_dir.mkdir(exist_ok=True)
        
        self.audio = None
        self.recognizer = sr.Recognizer()
        self._executor = ThreadPoolExecutor(max_workers=5)
        
        self.running = False
        self.active = False
        self.is_recording = False
        
        self.api_key = os.getenv("GOOGLE_API_KEY", "").strip()
        self.model = os.getenv("GEMINI_MODEL", "gemini-1.5-flash").strip()

        try:
            self.audio = pyaudio.PyAudio()
        except:
            print("❌ PyAudio failed to initialize")

    async def _run_in_executor(self, func, *args):
        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(self._executor, func, *args)

    def _is_silent(self, data):
        if not data: return True
        rms = math.sqrt(sum(x*x for x in data)/len(data))
        return rms < self.SILENCE_THRESHOLD

    def _record_sync(self):
        if not self.audio or not self.active: return None
        
        try:
            stream = self.audio.open(format=self.FORMAT, channels=self.CHANNELS,
                                   rate=self.RATE, input=True, frames_per_buffer=self.CHUNK)
            frames = []
            started = False
            silent_chunks = 0
            max_silent = int(self.SILENCE_DURATION * self.RATE / self.CHUNK)
            
            print("🎤 Listening...")
            start_time = time.time()
            
            while self.running and self.active:
                data = stream.read(self.CHUNK, exception_on_overflow=False)
                audio_data = [int.from_bytes(data[i:i+2], 'little', signed=True) for i in range(0, len(data), 2)]
                rms = math.sqrt(sum(x*x for x in audio_data)/len(audio_data)) if audio_data else 0
                
                if not started and rms > self.MIN_ENERGY_THRESHOLD:
                    started = True
                    print("🗣️ Speech detected")
                
                if started:
                    frames.append(data)
                    if rms < self.SILENCE_THRESHOLD:
                        silent_chunks += 1
                    else:
                        silent_chunks = 0
                    
                    if silent_chunks > max_silent:
                        break
                
                if time.time() - start_time > 15: # Max 15s recording
                    break
                    
            stream.stop_stream()
            stream.close()
            
            if len(frames) < 10: return None
            
            path = self.audio_dir / f"rec_{int(time.time())}.wav"
            wf = wave.open(str(path), 'wb')
            wf.setnchannels(self.CHANNELS)
            wf.setsampwidth(self.audio.get_sample_size(self.FORMAT))
            wf.setframerate(self.RATE)
            wf.writeframes(b''.join(frames))
            wf.close()
            return path
        except Exception as e:
            print(f"❌ Recording error: {e}")
            return None

    def _stt_sync(self, path):
        try:
            with sr.AudioFile(str(path)) as source:
                audio = self.recognizer.record(source)
            return self.recognizer.recognize_google(audio, language='tr-TR')
        except:
            return None

    def _gemini_sync(self, prompt):
        if not self.api_key: return "API key missing"
        
        url = f"https://generativelanguage.googleapis.com/v1/models/{self.model}:generateContent?key={self.api_key}"
        body = {
            "contents": [{"parts": [{"text": f"Kısa ve öz cevap ver. Soru: {prompt}"}]}]
        }
        
        try:
            resp = requests.post(url, json=body, timeout=10)
            if resp.status_code == 200:
                data = resp.json()
                return data['candidates'][0]['content']['parts'][0]['text']
            else:
                print(f"❌ Gemini Error {resp.status_code}: {resp.text}")
                return f"Hata: {resp.status_code}"
        except Exception as e:
            return f"Bağlantı hatası: {e}"

    def _tts_sync(self, text):
        try:
            path = self.audio_dir / f"resp_{int(time.time())}.mp3"
            tts = gTTS(text=text, lang='tr')
            tts.save(str(path))
            return path
        except:
            return None

    async def voice_loop(self):
        self.running = True
        while self.running:
            if not self.active:
                await asyncio.sleep(0.5)
                continue
            
            await broadcast_state("LISTENING")
            path = await self._run_in_executor(self._record_sync)
            
            if path and self.active:
                await broadcast_state("WAITING")
                
                text = await self._run_in_executor(self._stt_sync, path)
                if text:
                    print(f"👤 User: {text}")
                    response = await self._run_in_executor(self._gemini_sync, text)
                    print(f"🤖 AI: {response}")
                    
                    audio_path = await self._run_in_executor(self._tts_sync, response)
                    if audio_path:
                        # Serve via HTTP
                        url = f"http://localhost:8090/audio/{audio_path.name}"
                        await broadcast_speak(url, 5.0, response)
                        # App state will be IDLE after broadcast_speak handles the event
                
            await broadcast_state("IDLE")
            await asyncio.sleep(0.1)

    def start(self, loop):
        asyncio.create_task(self.voice_loop())

    def stop(self):
        self.running = False
        self.active = False

    def set_active(self, active):
        self.active = active
        print(f"🎤 Voice component: {'ACTIVE' if active else 'INACTIVE'}")
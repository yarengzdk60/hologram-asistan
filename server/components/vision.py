"""
Vision Component - Hand gesture detection using MediaPipe
"""
import cv2
import time
import base64
import asyncio
import numpy as np
from mediapipe.tasks import python
from mediapipe.tasks.python import vision
from mediapipe import Image, ImageFormat

from server.components.websocket import broadcast_action, broadcast_video_frame


class VisionComponent:
    """Hand gesture detection component"""

    def __init__(self):
        # MediaPipe Config - New API with model file
        # Model file downloaded for Python 3.10 compatibility
        from pathlib import Path
        model_path = Path(__file__).parent.parent.parent / "hand_landmarker.task"

        base_options = python.BaseOptions(model_asset_path=str(model_path))
        options = vision.HandLandmarkerOptions(
            base_options=base_options,
            running_mode=vision.RunningMode.VIDEO,
            num_hands=2,
            min_hand_detection_confidence=0.7,
            min_hand_presence_confidence=0.7,
            min_tracking_confidence=0.7
        )
        self.hand_landmarker = vision.HandLandmarker.create_from_options(options)
        # Wave Detection State
        self.prev_wrist_x = None
        self.wave_direction = 0
        self.wave_inflections = 0
        self.last_inflection_time = 0
        self.last_wave_trigger_time = 0
        # Constants
        self.MOVEMENT_THRESHOLD = 0.02
        self.WAVE_TIMEOUT = 0.5
        self.WAVE_COOLDOWN = 1.0

        self.cap = None
        self.running = False

    def is_hand_open(self, landmarks):
        """Check if hand is open based on finger positions"""
        tips = [8, 12, 16, 20]
        pips = [6, 10, 14, 18]
        open_fingers = 0

        for tip, pip in zip(tips, pips):
            if landmarks[tip].y < landmarks[pip].y:
                open_fingers += 1

        return open_fingers >= 2

    async def camera_loop_async(self, loop: asyncio.AbstractEventLoop):
        """Main camera processing loop (async version)"""
        try:
            # CAMERA GUARD: Don't reopen if already open
            if self.cap and self.cap.isOpened():
                print("📸 Camera already open - using existing stream")
                self.running = True
            else:
                print("📸 Attempting to open camera...")
                self.cap = cv2.VideoCapture(0, cv2.CAP_DSHOW)
                if not self.cap.isOpened():
                    print("❌ Cannot open camera - trying without CAP_DSHOW...")
                    self.cap = cv2.VideoCapture(0)
                    if not self.cap.isOpened():
                        print("❌ Cannot open camera - no camera found!")
                        return

                print("📸 Camera opened successfully")
                self.running = True

            while self.running:
                ret, frame = self.cap.read()
                if not ret:
                    print("⚠️ Failed to read frame from camera")
                    break

                frame = cv2.flip(frame, 1)
                rgb_frame = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
                mp_image = Image(image_format=ImageFormat.SRGB, data=rgb_frame)
                # Process with new API
                # Calculate timestamp in milliseconds
                timestamp_ms = int(time.time() * 1000)
                try:
                    detection_result = self.hand_landmarker.detect_for_video(mp_image, timestamp_ms)
                except Exception as e:
                    print(f"⚠️ MediaPipe detection error: {e}")
                    detection_result = type('obj', (object,), {'hand_landmarks': None})()

                # Gesture Detection
                if detection_result.hand_landmarks:
                    for hand_landmarks in detection_result.hand_landmarks:
                        # Draw landmarks (simplified - just draw points)
                        for landmark in hand_landmarks:
                            x = int(landmark.x * frame.shape[1])
                            y = int(landmark.y * frame.shape[0])
                            cv2.circle(frame, (x, y), 3, (0, 255, 0), -1)

                        lm = hand_landmarks

                        if not self.is_hand_open(lm):
                            self.wave_inflections = 0
                            self.wave_direction = 0
                            continue

                        wrist_x = lm[0].x
                        now = time.time()

                        if self.prev_wrist_x is not None:
                            dx = wrist_x - self.prev_wrist_x

                            if abs(dx) > self.MOVEMENT_THRESHOLD:
                                curr_dir = 1 if dx > 0 else -1

                                if self.wave_direction != 0 and curr_dir != self.wave_direction:
                                    self.wave_inflections += 1
                                    self.last_inflection_time = now
                                    print(f"🌊 Inflection: {self.wave_inflections}")
                                elif self.wave_direction == 0:
                                    self.last_inflection_time = now

                                self.wave_direction = curr_dir

                            if now - self.last_inflection_time > self.WAVE_TIMEOUT:
                                self.wave_inflections = 0
                                self.wave_direction = 0

                            if self.wave_inflections >= 2:
                                if now - self.last_wave_trigger_time > self.WAVE_COOLDOWN:
                                    await broadcast_action("wave")
                                    self.last_wave_trigger_time = now
                                    print("👋 WAVE CONFIRMED!")

                                self.wave_inflections = 0

                        self.prev_wrist_x = wrist_x

                else:
                    self.prev_wrist_x = None
                    self.wave_direction = 0
                    self.wave_inflections = 0

                # Frame Streaming
                _, buffer = cv2.imencode(
                    ".jpg", frame,
                    [int(cv2.IMWRITE_JPEG_QUALITY), 70]
                )

                frame_base64 = base64.b64encode(buffer).decode("utf-8")

                await broadcast_video_frame(frame_base64)

                await asyncio.sleep(0.02)

        except Exception as e:
            print(f"❌ Camera loop error: {e}")
            import traceback
            traceback.print_exc()
        finally:
            if self.cap:
                self.cap.release()
                print("📸 Camera released")

    def start(self, loop: asyncio.AbstractEventLoop):
        """Start the vision component"""
        if self.running:
            print("⚠️ Vision component already running")
            return
        print("👁️ Starting vision component...")
        asyncio.create_task(self.camera_loop_async(loop))

    def stop(self):
        """Stop the vision component"""
        self.running = False
        if self.cap:
            self.cap.release()
            self.cap = None
        print("👁️ Vision component stopped")

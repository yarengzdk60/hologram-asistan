"""
Vision Component - General Motion Detection using OpenCV Frame Differencing
"""
import cv2
import time
import asyncio
import numpy as np

from server.components.websocket import broadcast_action


class VisionComponent:
    """Motion detection component based on frame differencing"""

    def __init__(self):
        # Motion Detection Settings
        self.MOTION_THRESHOLD = 2000  # Non-zero pixels threshold
        self.MOTION_COOLDOWN = 1.2     # Cooldown in seconds before next event
        
        # State
        self.prev_gray = None
        self.last_motion_time = 0
        
        self.cap = None
        self.running = False

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

                # 1. Preprocessing
                frame = cv2.flip(frame, 1)
                gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
                gray = cv2.GaussianBlur(gray, (21, 21), 0)

                # Initialize previous frame if needed
                if self.prev_gray is None:
                    self.prev_gray = gray
                    continue

                # 2. Motion Detection (Frame Differencing)
                # Calculate absolute difference between current frame and previous frame
                frame_delta = cv2.absdiff(self.prev_gray, gray)
                # Apply threshold to highlight the differences
                thresh = cv2.threshold(frame_delta, 25, 255, cv2.THRESH_BINARY)[1]
                # Dilate the thresholded image to fill in holes
                thresh = cv2.dilate(thresh, None, iterations=2)

                # Count the number of non-zero pixels (movement)
                motion_count = cv2.countNonZero(thresh)
                
                # 3. Event Triggering with Cooldown
                now = time.time()
                if motion_count > self.MOTION_THRESHOLD:
                    if now - self.last_motion_time > self.MOTION_COOLDOWN:
                        print(f"🎬 Motion Detected: val={motion_count}")
                        try:
                            await broadcast_action("motion_detected")
                        except Exception as e:
                            print(f"⚠️ Failed to broadcast motion event: {e}")
                        self.last_motion_time = now

                # 4. Update previous frame and sleep
                self.prev_gray = gray
                
                # No video streaming to reduce overhead
                await asyncio.sleep(0.03) # Approx 30 FPS processing

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
        print("👁️ Starting motion-based vision component...")
        self.prev_gray = None # Reset state on start
        asyncio.create_task(self.camera_loop_async(loop))

    def stop(self):
        """Stop the vision component"""
        self.running = False
        if self.cap:
            self.cap.release()
            self.cap = None
        print("👁️ Vision component stopped")

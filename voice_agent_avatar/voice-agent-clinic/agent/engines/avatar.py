"""
Avatar engine — free/self-hosted real-time talking head.
Supports LivePortrait (open-source, GPU) for lip-sync avatar.
"""

import os
import asyncio
import logging
from typing import Optional, AsyncIterator
from collections import deque

import numpy as np

logger = logging.getLogger(__name__)



class LivePortraitEngine:
    """
    LivePortrait real-time avatar engine.
    Pipeline: Audio chunks → LivePortrait → Video frames
    Requires GPU (T4+).
    """

    def __init__(
        self,
        checkpoint_path: str = "/kaggle/working/LivePortrait/checkpoints",
        device: str = "cuda:0",
        reference_image_path: str = "/kaggle/working/reference_image.jpg",
    ):
        import torch
        import cv2

        self.device = device if torch.cuda.is_available() else "cpu"
        self.reference_image_path = reference_image_path

        import sys

        sys.path.insert(0, "/kaggle/working/LivePortrait")
        from src.live_portrait_pipeline import LivePortraitPipeline

        self.pipeline = LivePortraitPipeline(
            checkpoint_F=os.path.join(checkpoint_path, "appearance_feature_extractor.pth"),
            checkpoint_M=os.path.join(checkpoint_path, "motion_extractor.pth"),
            checkpoint_G=os.path.join(checkpoint_path, "generator.pth"),
            checkpoint_W=os.path.join(checkpoint_path, "warping_module.pth"),
            device=self.device,
        )

        self._prepare_reference()

        self.audio_buffer = deque(maxlen=16000)
        self.is_processing = False

        logger.info(f"LivePortrait engine initialized on {self.device}")

    def _prepare_reference(self):
        import cv2

        img = cv2.imread(self.reference_image_path)
        if img is None:
            raise ValueError(f"Could not load reference image: {self.reference_image_path}")

        img = cv2.resize(img, (512, 512))
        img = cv2.cvtColor(img, cv2.COLOR_BGR2RGB)

        self.source_image = img
        self.source_features = self.pipeline.prepare_source(img)
        logger.info("Reference image processed")

    async def process_audio_chunk(self, audio_chunk: np.ndarray) -> Optional[np.ndarray]:
        """Process audio chunk and generate video frame. Returns RGB frame or None."""
        if self.is_processing:
            return None

        self.is_processing = True
        try:
            self.audio_buffer.extend(audio_chunk)

            if len(self.audio_buffer) < 6400:
                return None

            recent_audio = np.array(list(self.audio_buffer)[-6400:])

            loop = asyncio.get_event_loop()
            frame = await loop.run_in_executor(None, lambda: self._generate_frame(recent_audio))
            return frame
        finally:
            self.is_processing = False

    def _generate_frame(self, audio: np.ndarray) -> np.ndarray:
        """Generate single video frame from audio."""
        motion = self.pipeline.extract_motion(audio)
        frame = self.pipeline.generate(self.source_features, motion)
        frame = (frame * 255).astype(np.uint8)
        return frame

    async def generate_video_stream(
        self, audio_generator, fps: int = 30
    ) -> AsyncIterator[bytes]:
        """Generate video frames from audio stream. Yields JPEG bytes."""
        import cv2

        frame_interval = 1.0 / fps

        async for audio_chunk in audio_generator:
            frame = await self.process_audio_chunk(audio_chunk)
            if frame is not None:
                _, buffer = cv2.imencode(".jpg", cv2.cvtColor(frame, cv2.COLOR_RGB2BGR))
                yield buffer.tobytes()

            await asyncio.sleep(frame_interval)

import os
import subprocess
import tempfile
from typing import List, Optional

import cv2
import numpy as np

MAX_DURATION_SECONDS = 10
MAX_FILE_SIZE_BYTES = 20 * 1024 * 1024  # 20MB

def compute_sharpness(frame: np.ndarray) -> float:
    """Compute the sharpness of a frame using the variance of the Laplacian."""
    gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
    return cv2.Laplacian(gray, cv2.CV_64F).var()

def extract_sharpest_frames(video_bytes: bytes, max_frames: int = 3) -> List[np.ndarray]:
    """
    Extract frames at 1 fps for up to MAX_DURATION_SECONDS.
    Return the top `max_frames` sharpest frames.
    """
    if len(video_bytes) > MAX_FILE_SIZE_BYTES:
        raise ValueError(f"Video file exceeds maximum size of {MAX_FILE_SIZE_BYTES / (1024*1024)}MB.")

    with tempfile.NamedTemporaryFile(delete=False, suffix=".mp4") as temp_video:
        temp_video.write(video_bytes)
        temp_path = temp_video.name

    frames = []
    try:
        cap = cv2.VideoCapture(temp_path)
        if not cap.isOpened():
            raise ValueError("Could not open video file.")

        fps = cap.get(cv2.CAP_PROP_FPS)
        if fps <= 0:
            fps = 30.0

        current_frame_idx = 0
        frames_extracted = 0

        while True:
            ret, frame = cap.read()
            if not ret:
                break

            # Extract 1 frame per second
            if current_frame_idx % int(fps) == 0:
                sharpness = compute_sharpness(frame)
                frames.append((sharpness, frame))
                frames_extracted += 1

                if frames_extracted >= MAX_DURATION_SECONDS:
                    break

            current_frame_idx += 1

        cap.release()
    finally:
        if os.path.exists(temp_path):
            os.remove(temp_path)

    if not frames:
        raise ValueError("Could not extract any frames from the video.")

    # Sort by sharpness descending and take top N
    frames.sort(key=lambda x: x[0], reverse=True)
    top_frames = [f[1] for f in frames[:max_frames]]
    
    return top_frames


def extract_audio_track(video_bytes: bytes) -> Optional[bytes]:
    """
    Extract a short mono WAV audio track from a video with ffmpeg when available.
    Returns None for silent videos, missing ffmpeg, or unsupported containers.
    """
    if len(video_bytes) > MAX_FILE_SIZE_BYTES:
        raise ValueError(f"Video file exceeds maximum size of {MAX_FILE_SIZE_BYTES / (1024*1024)}MB.")

    input_path = None
    output_path = None
    try:
        with tempfile.NamedTemporaryFile(delete=False, suffix=".mp4") as temp_video:
            temp_video.write(video_bytes)
            input_path = temp_video.name
        with tempfile.NamedTemporaryFile(delete=False, suffix=".wav") as temp_audio:
            output_path = temp_audio.name

        cmd = [
            "ffmpeg",
            "-y",
            "-v",
            "error",
            "-i",
            input_path,
            "-t",
            str(MAX_DURATION_SECONDS),
            "-vn",
            "-ac",
            "1",
            "-ar",
            "16000",
            output_path,
        ]
        result = subprocess.run(cmd, capture_output=True, timeout=30, check=False)
        if result.returncode != 0 or not output_path or not os.path.exists(output_path) or os.path.getsize(output_path) == 0:
            return None
        with open(output_path, "rb") as f:
            return f.read()
    except Exception:
        return None
    finally:
        for path in (input_path, output_path):
            if path and os.path.exists(path):
                try:
                    os.remove(path)
                except Exception:
                    pass

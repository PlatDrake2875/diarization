# utils.py
"""
Utility functions for the Speech Diarization Pipeline.
"""
import logging
import traceback
from typing import Union
import numpy as np
import soundfile as sf
from pathlib import Path

# Attempt to import IPython display for environments that support it
try:
    from IPython.display import Audio, display
    IPYTHON_AVAILABLE = True
except ImportError:
    IPYTHON_AVAILABLE = False

logger = logging.getLogger(__name__)

def create_dummy_audio_file(file_path: Union[str, Path] = "test_audio.wav",
                             duration: int = 10,
                             sample_rate: int = 16000) -> None:
    """
    Creates a dummy stereo WAV file with two distinct 'speakers' for testing.

    Args:
        file_path: Path where the dummy audio file will be saved.
        duration: Duration of the audio file in seconds.
        sample_rate: Sample rate of the audio file in Hz.
    """
    file_path_obj = Path(file_path)
    if not file_path_obj.exists():
        logger.info(f"Creating a dummy audio file at: {file_path_obj}")
        t = np.linspace(0, duration, int(sample_rate * duration), endpoint=False)
        # Speaker 1: Sine wave 220Hz from 0s to 45% of duration
        freq1 = 220
        audio1_end_sample = int(sample_rate * duration * 0.45)
        audio1 = 0.5 * np.sin(2 * np.pi * freq1 * t[:audio1_end_sample])

        # Speaker 2: Sine wave 330Hz from 50% to 95% of duration
        freq2 = 330
        audio2_start_sample = int(sample_rate * duration * 0.50)
        audio2_end_sample = int(sample_rate * duration * 0.95)
        audio2 = 0.5 * np.sin(2 * np.pi * freq2 * t[:(audio2_end_sample - audio2_start_sample)]) # Create correct length

        # Combine segments with silence in between
        combined_audio = np.zeros(int(sample_rate * duration))
        combined_audio[:len(audio1)] = audio1
        if len(audio2) > 0: # Ensure audio2 is not empty
             combined_audio[audio2_start_sample : audio2_start_sample + len(audio2)] = audio2

        # Make it stereo by stacking (optional, models usually handle mono/stereo)
        stereo_audio = np.stack([combined_audio, combined_audio * 0.8], axis=-1)
        try:
            # Write the audio data to a WAV file
            sf.write(file_path_obj, stereo_audio, sample_rate)
            logger.info(f"Dummy audio file '{file_path_obj}' created.")

            # Try displaying an audio player if in a suitable environment
            if IPYTHON_AVAILABLE:
                try:
                    display(Audio(data=stereo_audio.T, rate=sample_rate))
                except Exception as display_e:
                    logger.warning(f"Could not display audio player: {display_e}")
        except Exception as e:
            logger.error(f"Failed to create dummy audio file '{file_path_obj}': {e}")
            traceback.print_exc()
    else:
        logger.info(f"Dummy audio file {file_path_obj} already exists.")


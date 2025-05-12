# backend/config.py
"""
Configuration module for the Speech Diarization Pipeline.

Defines the DiarizationConfig class to hold all pipeline settings
and relevant constants.
"""
import os
import torch
import logging
from pathlib import Path
from typing import Optional, Union

# --- Constants ---
DEFAULT_DIARIZATION_MODEL = "pyannote/speaker-diarization-3.1"
DEFAULT_ASR_MODEL = "readerbench/whisper-ro" # User's preferred default
DEFAULT_OUTPUT_DIR = Path("./diarization_output_modular") # Default output location
DEFAULT_MIN_LENGTH_FOR_ASR_BATCHING_S = 600 # e.g., 10 minutes

logger = logging.getLogger(__name__)

class DiarizationConfig:
    """
    Configuration settings for the diarization pipeline.
    """
    def __init__(
        self,
        audio_file_path: Union[str, Path],
        output_dir: Union[str, Path] = DEFAULT_OUTPUT_DIR,
        hf_access_token: Optional[str] = None,
        device: Optional[Union[str, int]] = None,
        diarization_model: str = DEFAULT_DIARIZATION_MODEL,
        asr_model: str = DEFAULT_ASR_MODEL,
        use_gpu: bool = True,
        use_mps: bool = True,
        cache_dir: Optional[Union[str, Path]] = None,
        force_recompute_diarization: bool = False,
        force_recompute_asr: bool = False,
        whisper_batch_size: int = 16, # Batch size for Whisper model inference within each ASR chunk
        
        # ASR Batching Parameters
        enable_asr_batching: Optional[bool] = None, # None for auto-detect based on audio length
        min_audio_length_for_batching_s: int = DEFAULT_MIN_LENGTH_FOR_ASR_BATCHING_S,
        asr_processing_chunk_duration_s: int = 300,  # e.g., 5 minutes per ASR chunk
        asr_processing_chunk_overlap_s: int = 30,    # e.g., 30 seconds overlap between ASR chunks
    ):
        """
        Initializes the DiarizationConfig object.
        """
        self.audio_file_path = Path(audio_file_path).resolve()
        self.output_dir = Path(output_dir).resolve()
        self.hf_access_token = hf_access_token or os.getenv("HF_ACCESS_TOKEN")
        self.diarization_model = diarization_model
        self.asr_model = asr_model
        self.cache_dir = Path(cache_dir).resolve() if cache_dir else None
        self.force_recompute_diarization = force_recompute_diarization
        self.force_recompute_asr = force_recompute_asr
        self.whisper_batch_size = whisper_batch_size

        self.device = device if device is not None else self._detect_device(use_gpu, use_mps)

        if not self.hf_access_token and "pyannote" in self.diarization_model:
            logger.warning("Hugging Face access token not provided or found in environment variable HF_ACCESS_TOKEN. "
                           "Access to gated models like pyannote might fail.")

        self.output_dir.mkdir(parents=True, exist_ok=True)
        logger.info(f"Output directory set to: {self.output_dir}")

        self.diarization_cache_path = self.output_dir / f"{self.audio_file_path.stem}.diarization.pkl"
        logger.info(f"Diarization cache path: {self.diarization_cache_path}")

        # ASR Batching settings
        self.enable_asr_batching = enable_asr_batching
        self.min_audio_length_for_batching_s = min_audio_length_for_batching_s
        self.asr_processing_chunk_duration_s = asr_processing_chunk_duration_s
        self.asr_processing_chunk_overlap_s = asr_processing_chunk_overlap_s
        
        if self.enable_asr_batching is None: # Auto-detect if not explicitly set
            # This part requires getting audio duration.
            # We'll do this check in pipeline_core.py where audio info is available.
            logger.info("ASR batching mode will be auto-detected based on audio length.")
        elif self.enable_asr_batching:
            logger.info(f"ASR batching explicitly enabled. Chunk duration: {self.asr_processing_chunk_duration_s}s, Overlap: {self.asr_processing_chunk_overlap_s}s")
        else:
            logger.info("ASR batching explicitly disabled.")


    @staticmethod
    def _detect_device(use_gpu: bool, use_mps: bool) -> Union[str, int]:
        """Automatically selects the processing device."""
        if use_gpu and torch.cuda.is_available():
            device_idx = 0 
            logger.info(f"CUDA (GPU) detected. Using GPU device index: {device_idx}")
            return device_idx
        elif use_mps and hasattr(torch.backends, 'mps') and torch.backends.mps.is_available():
            logger.info("MPS (Apple Silicon GPU) detected. Using MPS.")
            return "mps"
        else:
            logger.info("No GPU or MPS detected/enabled. Using CPU.")
            return "cpu"

    @property
    def torch_dtype(self) -> torch.dtype:
        """Determines the torch data type based on the selected device."""
        if isinstance(self.device, int) and torch.cuda.is_available():
             logger.info("Using torch.float16 for GPU.")
             return torch.float16
        logger.info("Using torch.float32 for CPU or other devices.")
        return torch.float32

    @property
    def pipeline_device(self) -> str:
        """Returns the device string/index formatted for HF pipelines."""
        if isinstance(self.device, int):
            return f"cuda:{self.device}"
        return str(self.device) 

    @property
    def asr_cache_file_path(self) -> Path:
        """Dynamically generates the path for the ASR cache file."""
        asr_base_name = self.audio_file_path.stem
        model_name_slug = self.asr_model.replace('/','_')
        # If ASR batching is used, the cache might represent the full combined ASR.
        # Or, one could implement per-chunk caching, but that's more complex.
        # For now, one cache file for the potentially batched ASR result.
        asr_cache_filename = f"{asr_base_name}_{model_name_slug}.asr_batched.pkl" if self.enable_asr_batching else f"{asr_base_name}_{model_name_slug}.asr.pkl"
        return self.output_dir / asr_cache_filename

    @property
    def output_transcript_path(self) -> Path:
        """Dynamically generates the path for the final transcript file."""
        base_name = self.audio_file_path.stem
        model_name_slug = self.asr_model.replace('/','_')
        output_filename = f"{base_name}_{model_name_slug}.diarized_transcript.txt"
        return self.output_dir / output_filename

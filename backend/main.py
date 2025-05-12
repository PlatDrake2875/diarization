# main.py
"""
Main executable script for the Speech Diarization Pipeline.

This script parses command-line arguments, sets up the configuration,
initializes the pipeline components from other modules, and runs the
diarization and ASR process.
"""
import argparse
import logging
import sys # For exit codes
from pathlib import Path

import soundfile as sf # For reading audio file info

# Import custom modules
from config import DiarizationConfig, DEFAULT_ASR_MODEL, DEFAULT_DIARIZATION_MODEL, DEFAULT_OUTPUT_DIR
from pipeline_core import SpeechDiarizationPipeline
from utils import create_dummy_audio_file # Optional: if dummy file creation is needed

# --- Setup Global Logger ---
# Basic configuration is done here, can be overridden by specific module loggers if needed
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    datefmt='%Y-%m-%d %H:%M:%S'
)
logger = logging.getLogger(__name__) # Logger for this main script

def setup_arg_parser() -> argparse.ArgumentParser:
    """
    Configures and returns the command-line argument parser.

    Returns:
        argparse.ArgumentParser: The configured argument parser.
    """
    parser = argparse.ArgumentParser(
        description="Run Speaker Diarization and Automatic Speech Recognition (ASR) Pipeline.",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter # Shows default values in help
    )
    parser.add_argument(
        "audio_file",
        type=str,
        help="Path to the input audio file (e.g., audio/sample.wav)."
    )
    parser.add_argument(
        "-o", "--output-dir",
        type=str,
        default=str(DEFAULT_OUTPUT_DIR),
        help="Directory for output files (transcripts, cache)."
    )
    parser.add_argument(
        "--hf-token",
        type=str,
        default=None,
        help="Hugging Face API token. If not provided, tries to use HF_ACCESS_TOKEN environment variable."
    )
    parser.add_argument(
        "--asr-model",
        type=str,
        default=DEFAULT_ASR_MODEL,
        help="Name or path of the ASR model from Hugging Face Hub."
    )
    parser.add_argument(
        "--diarization-model",
        type=str,
        default=DEFAULT_DIARIZATION_MODEL,
        help="Name or path of the Pyannote diarization model from Hugging Face Hub."
    )
    parser.add_argument(
        "--device",
        type=str,
        default=None,
        help="Force processing device: 'cpu', 'mps', or a GPU index (e.g., '0'). Auto-detects if not set."
    )
    parser.add_argument(
        "--cache-dir",
        type=str,
        default=None,
        help="Path to a custom Hugging Face model cache directory."
    )
    parser.add_argument(
        "--batch-size",
        type=int,
        default=16,
        help="Batch size for ASR inference."
    )
    parser.add_argument(
        "--force-recompute-asr",
        action="store_true",
        help="Force ASR computation, ignoring any cached ASR results."
    )
    parser.add_argument(
        "--force-recompute-diarization",
        action="store_true",
        help="Force diarization computation, ignoring any cached diarization results."
    )
    parser.add_argument(
        "--no-gpu",
        action="store_false",
        dest="use_gpu", # store_false means use_gpu will be True by default
        help="Disable attempts to use GPU. If not set, GPU is preferred if available."
    )
    parser.add_argument(
        "--no-mps",
        action="store_false",
        dest="use_mps", # store_false means use_mps will be True by default
        help="Disable attempts to use MPS (Apple Silicon). If not set, MPS is preferred over CPU if available and no GPU."
    )
    # Example of adding a boolean flag for dummy file creation
    parser.add_argument(
        "--create-dummy",
        action="store_true",
        help="If specified and the input audio file is not found, create a dummy audio file for testing."
    )
    return parser

def run_pipeline_from_args(args: argparse.Namespace):
    """
    Sets up configuration and runs the diarization pipeline based on parsed arguments.

    Args:
        args: Parsed command-line arguments from argparse.
    """
    audio_file_path = Path(args.audio_file)

    # --- Pre-run Checks ---
    if not audio_file_path.is_file():
        if args.create_dummy:
            logger.warning(f"Audio file '{audio_file_path}' not found. Creating a dummy file as requested.")
            dummy_file_name = "dummy_audio_for_testing.wav"
            create_dummy_audio_file(file_path=dummy_file_name)
            audio_file_path = Path(dummy_file_name) # Update path to dummy file
            if not audio_file_path.is_file(): # Check if dummy creation failed
                logger.critical(f"Failed to create or find dummy audio file '{audio_file_path}'. Exiting.")
                sys.exit(1)
        else:
            logger.critical(f"Audio file '{audio_file_path}' not found. Use --create-dummy or provide a valid file. Exiting.")
            sys.exit(1)
    else:
        try:
            # sf.info needs a string path
            info = sf.info(str(audio_file_path))
            logger.info(f"Audio file properties: Path='{audio_file_path}', Duration={info.duration:.2f}s, "
                        f"Rate={info.samplerate}Hz, Channels={info.channels}")
            if info.samplerate != 16000:
                logger.warning(
                    f"Audio sample rate is {info.samplerate}Hz. Whisper models perform best with 16kHz. "
                    "Resampling may occur internally by the ASR pipeline."
                )
            logger.info(f"Audio has {info.channels} channel(s).")
        except Exception as e:
            logger.error(f"Could not read audio file properties for {audio_file_path}: {e}")
            sys.exit(1)

    # --- Pipeline Execution ---
    try:
        # Determine device based on args (handle integer conversion for GPU index)
        forced_device_arg = args.device
        if forced_device_arg is not None and forced_device_arg.isdigit():
             forced_device_arg = int(forced_device_arg)

        # Create configuration object
        config = DiarizationConfig(
            audio_file_path=audio_file_path,
            output_dir=args.output_dir,
            hf_access_token=args.hf_token,
            device=forced_device_arg,
            asr_model=args.asr_model,
            diarization_model=args.diarization_model,
            use_gpu=args.use_gpu,
            use_mps=args.use_mps,
            cache_dir=args.cache_dir,
            whisper_batch_size=args.batch_size,
            force_recompute_asr=args.force_recompute_asr,
            force_recompute_diarization=args.force_recompute_diarization
        )

        # Initialize and run the pipeline
        pipeline_runner = SpeechDiarizationPipeline(config)
        results = pipeline_runner.run()

        if results is not None:
            logger.info("Pipeline execution finished successfully.")
            sys.exit(0) # Success
        else:
            logger.error("Pipeline execution failed or was aborted.")
            sys.exit(1) # Failure

    except Exception as main_e:
        logger.critical(f"An unexpected critical error occurred in the main script: {main_e}", exc_info=True)
        sys.exit(1) # Failure

if __name__ == "__main__":
    FORCE_RECOMPUTE_ASR = True
    # Setup argument parser and parse arguments
    arg_parser = setup_arg_parser()
    cli_args = arg_parser.parse_args()

    # Run the pipeline with parsed arguments
    run_pipeline_from_args(cli_args)

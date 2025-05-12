# pipeline_core.py
"""
Core pipeline logic for Speech Diarization.

Contains the SpeechDiarizationPipeline class that orchestrates
diarization, ASR, and result combination.
"""
import logging
import pickle
import pprint
import traceback
from pathlib import Path
from typing import Optional, Dict, Any, List

import torch
from pyannote.audio import Pipeline as PyannoteDiarizationPipeline
from pyannote.audio.pipelines.utils.hook import ProgressHook
from pyannote.core import Annotation
from tqdm import tqdm
from transformers import pipeline as hf_pipeline

# Assuming config.py is in the same directory or accessible via PYTHONPATH
from config import DiarizationConfig # Import the config class

logger = logging.getLogger(__name__)

class SpeechDiarizationPipeline:
    """
    Orchestrates the speaker diarization and speech recognition pipeline.

    Loads models, performs inference, combines results, and saves the transcript.
    Uses configuration provided by a DiarizationConfig object.
    """
    def __init__(self, config: DiarizationConfig):
        """
        Initializes the pipeline with the given configuration.

        Args:
            config: A DiarizationConfig object containing pipeline settings.
        """
        self.config = config
        self._diarization_pipeline_instance: Optional[PyannoteDiarizationPipeline] = None
        self._asr_pipeline_instance: Optional[hf_pipeline] = None
        logger.info(f"Initialized SpeechDiarizationPipeline with ASR model: {config.asr_model}")

    @property
    def diarization_pipeline(self) -> PyannoteDiarizationPipeline:
        """Lazy loads and returns the pyannote diarization pipeline."""
        if self._diarization_pipeline_instance is None:
            logger.info(f"Loading diarization pipeline: {self.config.diarization_model}")
            try:
                self._diarization_pipeline_instance = PyannoteDiarizationPipeline.from_pretrained(
                    self.config.diarization_model,
                    use_auth_token=self.config.hf_access_token,
                    cache_dir=str(self.config.cache_dir) if self.config.cache_dir else None
                )
                if isinstance(self.config.device, int): 
                     torch_device = torch.device(self.config.pipeline_device)
                     self._diarization_pipeline_instance.to(torch_device)
                     logger.info(f"Moved diarization pipeline to {torch_device}")
                elif self.config.device == "mps":
                    try:
                        torch_device = torch.device("mps")
                        self._diarization_pipeline_instance.to(torch_device)
                        logger.info(f"Attempted to move diarization pipeline to {torch_device}")
                    except Exception as mps_e:
                         logger.warning(f"Could not move diarization pipeline to MPS: {mps_e}. Relying on default device placement.")
                logger.info("Diarization pipeline loaded successfully.")
            except Exception as e:
                logger.error(f"Error loading diarization pipeline: {e}")
                logger.error(f"Ensure model '{self.config.diarization_model}' exists and you have accepted terms if necessary.")
                traceback.print_exc()
                raise RuntimeError(f"Failed to load diarization model: {self.config.diarization_model}") from e
        return self._diarization_pipeline_instance

    @property
    def asr_pipeline(self) -> hf_pipeline:
        """Lazy loads and returns the Hugging Face ASR pipeline."""
        if self._asr_pipeline_instance is None:
            logger.info(f"Loading ASR pipeline: {self.config.asr_model}")
            try:
                torch_dtype = self.config.torch_dtype
                pipeline_device = self.config.pipeline_device
                logger.info(f"Using torch dtype: {torch_dtype} on pipeline device: {pipeline_device}")

                model_kwargs = {}
                if self.config.cache_dir:
                    model_kwargs['cache_dir'] = str(self.config.cache_dir)
                
                # model_kwargs['attn_implementation'] = "eager" 

                self._asr_pipeline_instance = hf_pipeline(
                    task="automatic-speech-recognition",
                    model=self.config.asr_model,
                    torch_dtype=torch_dtype,
                    device=pipeline_device,
                    model_kwargs=model_kwargs, 
                    token=self.config.hf_access_token if self.config.hf_access_token else None,
                    return_timestamps="word"
                )
                logger.info("ASR pipeline loaded successfully with return_timestamps='word'.")
            except Exception as e:
                logger.error(f"Error loading ASR pipeline: {e}")
                traceback.print_exc()
                raise RuntimeError(f"Failed to load ASR model: {self.config.asr_model}") from e
        return self._asr_pipeline_instance

    def _perform_diarization(self) -> Optional[Annotation]:
        """Performs speaker diarization, utilizing cache."""
        cache_path = self.config.diarization_cache_path
        if not self.config.force_recompute_diarization and cache_path.exists():
            logger.info(f"Loading cached diarization results from: {cache_path}")
            try:
                with open(cache_path, 'rb') as f:
                    diarization_result = pickle.load(f)
                if isinstance(diarization_result, Annotation):
                    logger.info("Cached diarization loaded successfully.")
                    return diarization_result
                else:
                    logger.warning("Cached diarization file contained unexpected object type. Recomputing...")
            except (pickle.UnpicklingError, EOFError, FileNotFoundError, Exception) as e:
                logger.warning(f"Could not load cached diarization file '{cache_path}' ({e}). Recomputing...")

        logger.info("Performing speaker diarization...")
        try:
            pipeline_to_run = self.diarization_pipeline
            logger.info(f"Applying diarization pipeline to: {self.config.audio_file_path}")
            with ProgressHook() as hook:
                diarization_result: Annotation = pipeline_to_run(
                    {"uri": self.config.audio_file_path.stem, "audio": str(self.config.audio_file_path)},
                    hook=hook,
                    num_speakers=None
                )
            logger.info(f"Saving diarization results to: {cache_path}")
            cache_path.parent.mkdir(parents=True, exist_ok=True)
            with open(cache_path, 'wb') as f:
                pickle.dump(diarization_result, f)
            logger.info("Diarization complete and saved.")
            return diarization_result
        except Exception as e:
            logger.error(f"Error during diarization processing: {e}")
            traceback.print_exc()
            return None

    def _perform_asr(self) -> Optional[Dict[str, Any]]:
        """Performs Automatic Speech Recognition, utilizing cache."""
        cache_path = self.config.asr_cache_file_path
        logger.info(f"ASR cache path determined as: {cache_path}")

        if not self.config.force_recompute_asr and cache_path.exists():
            logger.info(f"Loading cached ASR results from: {cache_path}")
            try:
                with open(cache_path, 'rb') as f:
                    asr_result = pickle.load(f)
                logger.info("Cached ASR results loaded successfully.")
                if isinstance(asr_result, dict) and "chunks" in asr_result:
                    return asr_result
                else:
                    logger.warning("Cached ASR result has unexpected format. Recomputing...")
            except (pickle.UnpicklingError, EOFError, FileNotFoundError, Exception) as e:
                logger.warning(f"Could not load cached ASR file '{cache_path}' ({e}). Recomputing...")

        logger.info("Performing speech recognition (ASR)...")
        asr_result = None
        try:
            pipeline_to_run = self.asr_pipeline
            logger.info(f"Calling ASR pipeline with audio: {self.config.audio_file_path} (using pipeline defaults for chunk/batch size)")
            
            try:
                asr_result = pipeline_to_run(str(self.config.audio_file_path))
                
                logger.info("--- RAW ASR Pipeline Result ---")
                result_str = pprint.pformat(asr_result)
                if len(result_str) > 2000: 
                     logger.info(result_str[:1000] + "\n...\n" + result_str[-1000:])
                else:
                     logger.info(result_str)
                logger.info("--- End RAW ASR Pipeline Result ---")

            except TypeError as e:
                if "'<=' not supported between instances of 'NoneType' and 'float'" in str(e) or \
                   "NoneType is not iterable" in str(e) or \
                   "can't convert NoneType to float" in str(e):
                    logger.error(f"Caught TypeError during ASR processing, likely due to timestamp prediction issues: {e}")
                    traceback.print_exc()
                    return None 
                raise 
            except Exception as e:
                logger.error(f"An unexpected error occurred during the ASR pipeline call: {e}")
                traceback.print_exc()
                return None

            if asr_result is None:
                 logger.error("ASR pipeline call failed or returned None.")
                 return None
            if not isinstance(asr_result, dict):
                 logger.warning(f"ASR pipeline returned unexpected result type: {type(asr_result)}")
                 return None
            if "chunks" not in asr_result: 
                 logger.warning("ASR result dictionary does not contain 'chunks' key (expected with word timestamps).")
                 if "text" in asr_result: 
                     logger.warning(f"ASR returned full text only: {asr_result['text']}")
                 return None

            logger.info(f"Saving ASR results to: {cache_path}")
            cache_path.parent.mkdir(parents=True, exist_ok=True)
            with open(cache_path, 'wb') as f:
                pickle.dump(asr_result, f)
            logger.info("ASR complete and saved.")
            return asr_result
        except Exception as e:
            logger.error(f"Error during ASR processing step: {e}")
            traceback.print_exc()
            return None

    def _get_speaker_for_word(self, diarization: Annotation, word_mid_time: float) -> str:
        """
        Finds the speaker label for a given time point using diarization.itertracks().
        This matches the logic in old_main.py.
        """
        try:
             for segment, _, speaker_label in diarization.itertracks(yield_label=True):
                  if segment.start <= word_mid_time < segment.end:
                      return speaker_label
        except Exception as iter_e:
             # Log the error but don't necessarily stop; UNKNOWN_SPEAKER is the fallback
             logger.error(f"Error during speaker lookup via itertracks at {word_mid_time:.2f}s: {iter_e}")
             
        return "UNKNOWN_SPEAKER" # Default if no speaker is found or an error occurs

    def _combine_results(self, diarization_result: Annotation, asr_result: Dict[str, Any]) -> List[Dict[str, Any]]:
        """Combines speaker diarization labels with ASR word timestamps."""
        logger.info("Combining diarization and ASR results...")
        word_chunks = asr_result.get("chunks")

        if not isinstance(word_chunks, list) or not word_chunks:
            logger.error("Cannot combine results: ASR 'chunks' are missing, not a list, or empty.")
            logger.error(f"Problematic ASR result structure: {pprint.pformat(asr_result)}")
            return []

        final_segments: List[Dict[str, Any]] = []
        current_segment: Optional[Dict[str, Any]] = None
        logger.info(f"Aligning {len(word_chunks)} words to speaker segments...")

        for i, word_info in enumerate(tqdm(word_chunks, desc="Aligning words")):
            if not isinstance(word_info, dict):
                logger.warning(f"Skipping invalid word_info item (not a dict) at index {i}: {word_info}")
                continue
            
            word_text = word_info.get('text', '') 
            timestamp_tuple = word_info.get('timestamp')

            if not isinstance(timestamp_tuple, tuple) or len(timestamp_tuple) != 2:
                logger.warning(f"Skipping word {i} ('{word_text}') with invalid timestamp tuple: {timestamp_tuple}")
                continue
            
            word_start, word_end = timestamp_tuple
            
            if not (isinstance(word_start, (int, float)) and isinstance(word_end, (int, float))):
                 logger.warning(f"Skipping word {i} ('{word_text}') with non-numeric timestamp values: start={word_start}, end={word_end}")
                 continue
            
            if word_end <= word_start: 
                logger.warning(f"Word {i} ('{word_text}') has end time ({word_end:.2f}s) <= start time ({word_start:.2f}s). Adjusting end time to start_time + 0.1s for minimal duration.")
                word_end = word_start + 0.1 

            word_mid_time = word_start + (word_end - word_start) / 2.0
            active_speaker = self._get_speaker_for_word(diarization_result, word_mid_time)
            word_text_to_add = str(word_text) 

            if current_segment is None:
                current_segment = {"speaker": active_speaker, "text": word_text_to_add, "start_time": word_start, "end_time": word_end}
            elif current_segment["speaker"] == active_speaker:
                current_segment["text"] += word_text_to_add
                current_segment["end_time"] = word_end 
            else:
                current_segment["text"] = current_segment["text"].strip()
                if current_segment["text"]: 
                    final_segments.append(current_segment)
                current_segment = {"speaker": active_speaker, "text": word_text_to_add, "start_time": word_start, "end_time": word_end}

        if current_segment is not None:
            current_segment["text"] = current_segment["text"].strip()
            if current_segment["text"]:
                final_segments.append(current_segment)
        
        logger.info(f"Combined results into {len(final_segments)} final segments.")
        return final_segments

    def _save_transcript(self, final_segments: List[Dict[str, Any]]):
        """Saves the final list of diarized segments to a text file."""
        output_path = self.config.output_transcript_path
        logger.info(f"Transcript output path: {output_path}")
        logger.info(f"Saving {len(final_segments)} segments to: {output_path}")
        try:
            output_path.parent.mkdir(parents=True, exist_ok=True)
            with open(output_path, 'w', encoding='utf-8') as f:
                if not final_segments:
                    f.write("No speech segments identified or combined.\n")
                    logger.warning("Transcript empty. File saved with no segments message.")
                    return
                for seg in final_segments:
                    text = seg.get('text', '').strip()
                    speaker = seg.get('speaker', 'UNKNOWN_SPEAKER')
                    start = seg.get('start_time', 0.0)
                    end = seg.get('end_time', 0.0)
                    if text: 
                        line = f"[{speaker}] ({start:.2f}s - {end:.2f}s): {text}"
                        f.write(line + '\n')
            logger.info(f"Transcript saved to {output_path}")
        except IOError as e:
            logger.error(f"IOError saving transcript to '{output_path}': {e}")
            print("\n--- Diarized Transcript (Failed to Save, Console Fallback) ---")
            if not final_segments: print("No segments generated.")
            else:
                for seg_fb in final_segments:
                    text_fb, spk_fb = seg_fb.get('text','').strip(), seg_fb.get('speaker','UNK')
                    st_fb, et_fb = seg_fb.get('start_time',0.0), seg_fb.get('end_time',0.0)
                    if text_fb: print(f"[{spk_fb}] ({st_fb:.2f}s - {et_fb:.2f}s): {text_fb}")

    def run(self) -> Optional[List[Dict[str, Any]]]:
        """Executes the full diarization and ASR pipeline."""
        logger.info(f"Starting pipeline for: {self.config.audio_file_path}")
        logger.info(f"Device: {self.config.pipeline_device}, ASR: {self.config.asr_model}, Diarization: {self.config.diarization_model}")

        if not self.config.audio_file_path.is_file():
            logger.error(f"Audio file not found: {self.config.audio_file_path}")
            return None

        diarization_result = self._perform_diarization()
        if diarization_result is None:
            logger.error("Diarization failed. Aborting.")
            return None
        logger.info("Diarization step completed.")

        asr_result = self._perform_asr()
        if asr_result is None: 
             logger.error("ASR failed critically. Aborting.")
             return None
        
        word_chunks = asr_result.get("chunks")
        if not isinstance(word_chunks, list): 
            logger.error("ASR result 'chunks' is not a list. Aborting.")
            return None
        if not word_chunks: 
             logger.warning("ASR found no words ('chunks' is empty).")
             self._save_transcript([]) 
             return [] 
        logger.info("ASR step completed.")

        final_segments = self._combine_results(diarization_result, asr_result)
        logger.info("Combination step completed.")
        
        self._save_transcript(final_segments)

        print("\n--- Diarized Transcript (Console Output) ---")
        if not final_segments: print("No segments generated/combined.")
        else:
            for seg in final_segments:
                text, spk = seg.get('text','').strip(), seg.get('speaker','UNK')
                st, et = seg.get('start_time',0.0), seg.get('end_time',0.0)
                if text: print(f"[{spk}] ({st:.2f}s - {et:.2f}s): {text}")
        
        logger.info("Pipeline finished successfully.")
        return final_segments

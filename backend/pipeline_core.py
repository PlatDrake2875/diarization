# backend/pipeline_core.py
import logging
import pickle
import pprint
import traceback
from pathlib import Path
from typing import Optional, Dict, Any, List
import tempfile # For temporary chunk files

import torch
import soundfile as sf
from pydub import AudioSegment # For loading and slicing audio
from pydub.exceptions import CouldntDecodeError

from pyannote.audio import Pipeline as PyannoteDiarizationPipeline
from pyannote.core import Annotation
from tqdm import tqdm
from transformers import pipeline as hf_pipeline

from config import DiarizationConfig

logger = logging.getLogger(__name__)

class SpeechDiarizationPipeline:
    def __init__(self, config: DiarizationConfig):
        self.config = config
        self._diarization_pipeline_instance: Optional[PyannoteDiarizationPipeline] = None
        self._asr_pipeline_instance: Optional[hf_pipeline] = None
        self._audio_duration_s: Optional[float] = None # To store audio duration
        logger.info(f"Initialized SpeechDiarizationPipeline with ASR model: {config.asr_model}")

        # Determine if ASR batching should be enabled
        if self.config.enable_asr_batching is None: # Auto-detect
            try:
                info = sf.info(str(self.config.audio_file_path))
                self._audio_duration_s = info.duration
                if self._audio_duration_s > self.config.min_audio_length_for_batching_s:
                    self.config.enable_asr_batching = True
                    logger.info(f"Audio duration ({self._audio_duration_s:.2f}s) > min for batching ({self.config.min_audio_length_for_batching_s}s). ASR batching enabled.")
                else:
                    self.config.enable_asr_batching = False
                    logger.info(f"Audio duration ({self._audio_duration_s:.2f}s) <= min for batching. ASR batching disabled.")
            except Exception as e:
                logger.warning(f"Could not get audio duration to auto-detect ASR batching: {e}. Disabling ASR batching.")
                self.config.enable_asr_batching = False
        
        if self.config.enable_asr_batching:
             logger.info(f"ASR Batching final status: ENABLED. Chunk: {self.config.asr_processing_chunk_duration_s}s, Overlap: {self.config.asr_processing_chunk_overlap_s}s")
        else:
             logger.info("ASR Batching final status: DISABLED.")


    @property
    def diarization_pipeline(self) -> PyannoteDiarizationPipeline:
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
                logger.error(f"Error loading diarization pipeline: {e}", exc_info=True)
                raise RuntimeError(f"Failed to load diarization model: {self.config.diarization_model}") from e
        return self._diarization_pipeline_instance

    @property
    def asr_pipeline(self) -> hf_pipeline:
        if self._asr_pipeline_instance is None:
            logger.info(f"Loading ASR pipeline: {self.config.asr_model}")
            try:
                torch_dtype = self.config.torch_dtype
                pipeline_device = self.config.pipeline_device
                logger.info(f"Using torch dtype: {torch_dtype} on pipeline device: {pipeline_device}")
                model_kwargs = {'cache_dir': str(self.config.cache_dir)} if self.config.cache_dir else {}
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
                logger.error(f"Error loading ASR pipeline: {e}", exc_info=True)
                raise RuntimeError(f"Failed to load ASR model: {self.config.asr_model}") from e
        return self._asr_pipeline_instance

    def _perform_diarization(self) -> Optional[Annotation]:
        cache_path = self.config.diarization_cache_path
        if not self.config.force_recompute_diarization and cache_path.exists():
            logger.info(f"Loading cached diarization results from: {cache_path}")
            try:
                with open(cache_path, 'rb') as f: diarization_result = pickle.load(f)
                if isinstance(diarization_result, Annotation):
                    logger.info("Cached diarization loaded successfully.")
                    return diarization_result
                else: logger.warning("Cached diarization file invalid. Recomputing...")
            except Exception as e: logger.warning(f"Could not load cached diarization: {e}. Recomputing...")

        logger.info("Performing speaker diarization on full audio...")
        try:
            pipeline_to_run = self.diarization_pipeline
            diarization_result: Annotation = pipeline_to_run(
                {"uri": self.config.audio_file_path.stem, "audio": str(self.config.audio_file_path)},
                num_speakers=None
            )
            logger.info("Diarization processing finished.")
            with open(cache_path, 'wb') as f: pickle.dump(diarization_result, f)
            logger.info(f"Diarization complete and saved to {cache_path}.")
            return diarization_result
        except Exception as e:
            logger.error(f"Error during full audio diarization: {e}", exc_info=True)
            return None

    def _perform_asr_on_chunk(self, audio_chunk_path: Path, chunk_offset_s: float) -> List[Dict[str, Any]]:
        """Runs ASR on a single audio chunk and adjusts timestamps."""
        logger.info(f"Performing ASR on chunk: {audio_chunk_path.name}, offset: {chunk_offset_s:.2f}s")
        asr_chunk_result = self.asr_pipeline(str(audio_chunk_path))
        
        adjusted_word_segments = []
        if asr_chunk_result and "chunks" in asr_chunk_result:
            for word_segment in asr_chunk_result["chunks"]:
                if word_segment.get('timestamp'):
                    start_orig, end_orig = word_segment['timestamp']
                    # Ensure timestamps are valid floats before adding offset
                    if isinstance(start_orig, (int, float)) and isinstance(end_orig, (int, float)):
                        adjusted_segment = word_segment.copy()
                        adjusted_segment['timestamp'] = (
                            round(start_orig + chunk_offset_s, 3), 
                            round(end_orig + chunk_offset_s, 3)
                        )
                        adjusted_word_segments.append(adjusted_segment)
                    else:
                        logger.warning(f"Skipping word segment with invalid timestamp types in chunk {audio_chunk_path.name}: {word_segment['timestamp']}")
                else:
                    logger.warning(f"Word segment missing timestamp in chunk {audio_chunk_path.name}: {word_segment.get('text', 'N/A')}")
        logger.info(f"ASR for chunk {audio_chunk_path.name} produced {len(adjusted_word_segments)} adjusted word segments.")
        return adjusted_word_segments

    def _perform_asr(self) -> Optional[Dict[str, Any]]:
        cache_path = self.config.asr_cache_file_path
        if not self.config.force_recompute_asr and cache_path.exists():
            logger.info(f"Loading cached ASR results from: {cache_path}")
            try:
                with open(cache_path, 'rb') as f: asr_result = pickle.load(f)
                if isinstance(asr_result, dict) and "chunks" in asr_result:
                    logger.info("Cached ASR results loaded successfully.")
                    return asr_result
                else: logger.warning("Cached ASR file invalid. Recomputing...")
            except Exception as e: logger.warning(f"Could not load cached ASR: {e}. Recomputing...")

        if not self.config.enable_asr_batching:
            logger.info("Performing ASR on full audio (batching disabled)...")
            try:
                asr_result = self.asr_pipeline(str(self.config.audio_file_path))
            except Exception as e:
                logger.error(f"Error during full audio ASR: {e}", exc_info=True)
                return None
        else:
            logger.info("Performing ASR in batches...")
            all_word_segments = []
            full_text_parts = []
            try:
                logger.info(f"Loading full audio for ASR batching: {self.config.audio_file_path}")
                audio = AudioSegment.from_file(str(self.config.audio_file_path))
                duration_ms = len(audio)
                logger.info(f"Full audio loaded. Duration: {duration_ms / 1000.0:.2f}s")

                chunk_duration_ms = self.config.asr_processing_chunk_duration_s * 1000
                overlap_ms = self.config.asr_processing_chunk_overlap_s * 1000
                step_ms = chunk_duration_ms - overlap_ms

                for i_start_ms in range(0, duration_ms, step_ms):
                    i_end_ms = min(i_start_ms + chunk_duration_ms, duration_ms)
                    chunk_offset_s = i_start_ms / 1000.0
                    
                    logger.info(f"Processing ASR chunk: {chunk_offset_s:.2f}s - {i_end_ms / 1000.0:.2f}s")
                    audio_chunk = audio[i_start_ms:i_end_ms]

                    # Save chunk to a temporary WAV file
                    with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as tmp_chunk_file:
                        temp_chunk_path = Path(tmp_chunk_file.name)
                    
                    try:
                        audio_chunk.export(temp_chunk_path, format="wav")
                        logger.debug(f"Exported chunk to {temp_chunk_path}")
                        
                        chunk_word_segments = self._perform_asr_on_chunk(temp_chunk_path, chunk_offset_s)
                        
                        # Simple text assembly (can be improved for better overlap handling)
                        chunk_text = " ".join([s['text'] for s in chunk_word_segments if s.get('text')]).strip()
                        if chunk_text: full_text_parts.append(chunk_text)

                        # Handle overlap:
                        # For simplicity, we'll take all words from the first chunk.
                        # For subsequent chunks, we'll only take words whose start time is after the previous chunk's effective end
                        # (i.e., after the non-overlapping part of the previous chunk).
                        # A more sophisticated approach would involve word alignment in overlaps.
                        
                        effective_chunk_start_s = chunk_offset_s
                        if all_word_segments: # If not the first chunk
                            # Consider start of non-overlapping part of current chunk
                            effective_chunk_start_s = chunk_offset_s + self.config.asr_processing_chunk_overlap_s / 2.0 # Mid-point of overlap

                        for seg in chunk_word_segments:
                            # Add segment if its start time is within the "new" part of this chunk
                            if not all_word_segments or seg['timestamp'][0] >= effective_chunk_start_s:
                                all_word_segments.append(seg)
                            # Or if it's the very first word of a chunk that might have been missed
                            elif not any(existing_seg['timestamp'][0] == seg['timestamp'][0] and existing_seg['text'] == seg['text'] for existing_seg in all_word_segments):
                                # Avoid exact duplicates if a simpler overlap strategy is used
                                # This simple check might not be perfect for all ASR model outputs
                                pass # For now, a simpler approach is to just filter by start time

                    finally:
                        if temp_chunk_path.exists(): # Ensure temporary file is deleted
                            temp_chunk_path.unlink()
                            logger.debug(f"Deleted temp chunk {temp_chunk_path}")
                    
                    if i_end_ms == duration_ms:
                        break 
                
                # Deduplicate based on timestamp and text (basic)
                # This is a simple deduplication; more advanced methods might be needed for perfect stitching
                unique_segments = []
                seen_timestamps_texts = set()
                for seg in sorted(all_word_segments, key=lambda x: x['timestamp'][0]):
                    key = (seg['timestamp'][0], seg['timestamp'][1], seg['text'])
                    if key not in seen_timestamps_texts:
                        unique_segments.append(seg)
                        seen_timestamps_texts.add(key)
                all_word_segments = unique_segments

                asr_result = {"chunks": all_word_segments, "text": " ".join(full_text_parts)}

            except CouldntDecodeError: # From pydub
                logger.error(f"Pydub CouldntDecodeError: Failed to load/process the main audio file {self.config.audio_file_path}. It might be corrupted or FFmpeg is missing/misconfigured.", exc_info=True)
                return None
            except Exception as e:
                logger.error(f"Error during batched ASR processing: {e}", exc_info=True)
                return None

        if asr_result is None or "chunks" not in asr_result:
            logger.error("ASR processing failed to produce valid chunks.")
            return None

        with open(cache_path, 'wb') as f: pickle.dump(asr_result, f)
        logger.info(f"ASR complete and saved to {cache_path}.")
        return asr_result

    def _get_speaker_for_word(self, diarization: Annotation, word_mid_time: float) -> str:
        try:
             for segment, _, speaker_label in diarization.itertracks(yield_label=True):
                  if segment.start <= word_mid_time < segment.end:
                      return speaker_label
        except Exception as iter_e:
             logger.error(f"Error during speaker lookup via itertracks at {word_mid_time:.2f}s: {iter_e}", exc_info=True)
        return "UNKNOWN_SPEAKER"

    def _combine_results(self, diarization_result: Annotation, asr_result: Dict[str, Any]) -> List[Dict[str, Any]]:
        logger.info("Combining diarization and ASR results...")
        word_chunks = asr_result.get("chunks")
        if not isinstance(word_chunks, list) or not word_chunks:
            logger.error("Cannot combine: ASR 'chunks' are missing, not a list, or empty.", exc_info=True)
            return []

        final_segments: List[Dict[str, Any]] = []
        current_segment: Optional[Dict[str, Any]] = None
        logger.info(f"Aligning {len(word_chunks)} words to speaker segments...")

        for i, word_info in enumerate(tqdm(word_chunks, desc="Aligning words")):
            if not isinstance(word_info, dict):
                logger.warning(f"Skipping invalid word_info (not dict) at index {i}: {word_info}")
                continue
            word_text = word_info.get('text', '') 
            timestamp_tuple = word_info.get('timestamp')
            if not isinstance(timestamp_tuple, tuple) or len(timestamp_tuple) != 2:
                logger.warning(f"Skipping word {i} ('{word_text}') with invalid timestamp: {timestamp_tuple}")
                continue
            word_start, word_end = timestamp_tuple
            if not (isinstance(word_start, (int, float)) and isinstance(word_end, (int, float))):
                 logger.warning(f"Skipping word {i} ('{word_text}') with non-numeric timestamps: start={word_start}, end={word_end}")
                 continue
            if word_end <= word_start: 
                logger.debug(f"Word {i} ('{word_text}') has end time ({word_end:.2f}s) <= start time ({word_start:.2f}s). Adjusting end time to start_time + 0.1s.")
                word_end = word_start + 0.1 
            word_mid_time = word_start + (word_end - word_start) / 2.0
            active_speaker = self._get_speaker_for_word(diarization_result, word_mid_time)
            word_text_to_add = str(word_text) 
            if current_segment is None:
                current_segment = {"speaker": active_speaker, "text": word_text_to_add, "start_time": word_start, "end_time": word_end}
            elif current_segment["speaker"] == active_speaker and (word_start - current_segment["end_time"] < 1.0): # Merge if same speaker and small gap
                current_segment["text"] += word_text_to_add
                current_segment["end_time"] = word_end 
            else:
                current_segment["text"] = current_segment["text"].strip()
                if current_segment["text"]: final_segments.append(current_segment)
                current_segment = {"speaker": active_speaker, "text": word_text_to_add, "start_time": word_start, "end_time": word_end}
        if current_segment is not None and current_segment["text"].strip():
            final_segments.append(current_segment)
        logger.info(f"Combined results into {len(final_segments)} final segments.")
        return final_segments

    def _save_transcript(self, final_segments: List[Dict[str, Any]]):
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
                    text, speaker = seg.get('text','').strip(), seg.get('speaker','UNK')
                    start, end = seg.get('start_time',0.0), seg.get('end_time',0.0)
                    if text: f.write(f"[{speaker}] ({start:.2f}s - {end:.2f}s): {text}\n")
            logger.info(f"Transcript saved to {output_path}")
        except IOError as e:
            logger.error(f"IOError saving transcript to '{output_path}': {e}", exc_info=True)
            # Fallback print to console
            print("\n--- Diarized Transcript (Failed to Save, Console Fallback) ---")
            if not final_segments: print("No segments generated.")
            else:
                for seg_fb in final_segments:
                    text_fb, spk_fb = seg_fb.get('text','').strip(), seg_fb.get('speaker','UNK')
                    st_fb, et_fb = seg_fb.get('start_time',0.0), seg_fb.get('end_time',0.0)
                    if text_fb: print(f"[{spk_fb}] ({st_fb:.2f}s - {et_fb:.2f}s): {text_fb}")


    def run(self) -> Optional[List[Dict[str, Any]]]:
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
        if not word_chunks and not asr_result.get("text"): # If no chunks and no full text either
             logger.warning("ASR found no words or text ('chunks' is empty).")
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

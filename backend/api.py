# backend/api.py
import os
import uuid
import logging
from pathlib import Path
from flask import Flask, request, jsonify
from flask_cors import CORS
import yt_dlp 
from pydub import AudioSegment
from pydub.exceptions import CouldntDecodeError

from config import DiarizationConfig
from pipeline_core import SpeechDiarizationPipeline

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    datefmt='%Y-%m-%d %H:%M:%S'
)
api_logger = logging.getLogger(__name__)

app = Flask(__name__)
CORS(app)

BACKEND_DIR = Path(__file__).resolve().parent
UPLOAD_FOLDER = BACKEND_DIR / 'uploads'
YOUTUBE_DOWNLOADS_FOLDER = BACKEND_DIR / 'youtube_downloads'
RESULTS_FOLDER = BACKEND_DIR / 'diarization_results'

UPLOAD_FOLDER.mkdir(parents=True, exist_ok=True)
YOUTUBE_DOWNLOADS_FOLDER.mkdir(parents=True, exist_ok=True)
RESULTS_FOLDER.mkdir(parents=True, exist_ok=True)

def cleanup_files(*file_paths: Path):
    for file_path in file_paths:
        try:
            if file_path and file_path.exists():
                file_path.unlink()
                api_logger.info(f"Cleaned up temporary file: {file_path}")
        except Exception as e:
            api_logger.error(f"Error cleaning up file {file_path}: {e}")

@app.route('/api/download_youtube_audio', methods=['POST'])
def download_youtube_audio_route():
    api_logger.info("Received request to /api/download_youtube_audio")
    data = request.get_json()
    if not data or 'youtube_url' not in data:
        api_logger.warning("Missing youtube_url in request body")
        return jsonify({"error": "Missing youtube_url in request body"}), 400

    youtube_url = data['youtube_url']
    request_id = str(uuid.uuid4())
    api_logger.info(f"Processing request ID: {request_id} for URL: {youtube_url}")
    
    expected_downloaded_filename = f"{request_id}.wav"
    downloaded_audio_path = YOUTUBE_DOWNLOADS_FOLDER / expected_downloaded_filename
    output_template_for_yt_dlp = str(YOUTUBE_DOWNLOADS_FOLDER / f"{request_id}.%(ext)s")

    # --- Progress Hook for yt-dlp (less spammy) ---
    last_logged_percent = -10 # Initialize to ensure first log at 0% or more

    def my_hook(d):
        nonlocal last_logged_percent
        if d['status'] == 'downloading':
            try:
                percent_str = d.get('_percent_str', '0%').replace('%', '')
                current_percent = float(percent_str)
                # Log roughly every 10% or if it's the first/last update for downloading
                if current_percent >= last_logged_percent + 10 or current_percent == 0 or current_percent == 100:
                    api_logger.info(
                        f"[{request_id}] yt-dlp download: {d.get('_percent_str', 'N/A'):>5} "
                        f"of {d.get('_total_bytes_str', 'N/A'):<10} "
                        f"at {d.get('_speed_str', 'N/A'):<12} "
                        f"ETA {d.get('_eta_str', 'N/A')}"
                    )
                    last_logged_percent = current_percent if current_percent < 100 else -10 # Reset for next potential download in batch (not applicable here)
            except ValueError:
                api_logger.debug(f"[{request_id}] yt-dlp hook (downloading): {d.get('_percent_str', 'N/A')}") # Fallback log if percent parsing fails
        elif d['status'] == 'finished':
            api_logger.info(f"[{request_id}] yt-dlp: Finished downloading '{d.get('filename', 'N/A')}'. Now post-processing...")
            last_logged_percent = -10 # Reset for next file/stage
        elif d['status'] == 'error':
            api_logger.error(f"[{request_id}] yt-dlp: Error during processing. Info: {d.get('filename', 'N/A')}")


    try:
        api_logger.info(f"[{request_id}] Setting yt-dlp options to download and convert to WAV...")
        ydl_opts = {
            'format': 'bestaudio/best',
            'outtmpl': output_template_for_yt_dlp,
            'noplaylist': True,
            'quiet': False, 
            'verbose': False, 
            'nocheckcertificate': True,
            'postprocessors': [{
                'key': 'FFmpegExtractAudio',
                'preferredcodec': 'wav',
                'preferredquality': '0', 
            }],
            'progress_hooks': [my_hook], # Use the custom, less spammy hook
            'ffmpeg_location': os.getenv('FFMPEG_PATH')
        }
        
        api_logger.info(f"[{request_id}] Initializing YoutubeDL with options: {ydl_opts}")
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            api_logger.info(f"[{request_id}] Starting audio download and WAV conversion from: {youtube_url}")
            info_dict = ydl.extract_info(youtube_url, download=True)
            api_logger.info(f"[{request_id}] yt-dlp extract_info call completed. FFmpeg (if used by yt-dlp for WAV) should have run.")

        api_logger.info(f"[{request_id}] yt-dlp processing block finished. Checking for WAV file: {downloaded_audio_path}")
        
        if not downloaded_audio_path.exists():
            api_logger.error(f"[{request_id}] CRITICAL: Expected WAV file {downloaded_audio_path} not found after yt-dlp processing.")
            dir_contents = [str(p) for p in YOUTUBE_DOWNLOADS_FOLDER.iterdir() if p.name.startswith(request_id)]
            api_logger.debug(f"[{request_id}] Relevant contents of {YOUTUBE_DOWNLOADS_FOLDER}: {dir_contents}")
            intermediate_files = list(YOUTUBE_DOWNLOADS_FOLDER.glob(f"{request_id}.*"))
            if intermediate_files:
                api_logger.warning(f"[{request_id}] Intermediate files found: {intermediate_files}. WAV conversion by yt-dlp might have failed silently.")
            return jsonify({"error": "Failed to produce WAV file from YouTube audio."}), 500

        api_logger.info(f"[{request_id}] Successfully obtained WAV file: {downloaded_audio_path}")

        api_logger.info(f"[{request_id}] Verifying and standardizing WAV format with pydub: {downloaded_audio_path}")
        try:
            audio = AudioSegment.from_wav(downloaded_audio_path)
        except CouldntDecodeError:
            api_logger.error(f"[{request_id}] pydub CouldntDecodeError: The file {downloaded_audio_path} might not be a valid WAV or FFmpeg is missing/misconfigured for pydub.")
            return jsonify({"error": "Failed to read the downloaded WAV file. It might be corrupted or FFmpeg is not found by pydub."}), 500

        api_logger.info(f"[{request_id}] Loaded '{downloaded_audio_path.name}' with pydub. Duration: {len(audio) / 1000.0:.2f}s, Channels: {audio.channels}, Frame Rate: {audio.frame_rate}Hz")
        
        needs_resave = False
        if audio.channels > 1:
            api_logger.info(f"[{request_id}] Audio has {audio.channels} channels. Converting to mono.")
            audio = audio.set_channels(1)
            needs_resave = True
        
        target_frame_rate = 16000
        if audio.frame_rate != target_frame_rate:
            api_logger.info(f"[{request_id}] Audio frame rate is {audio.frame_rate}Hz. Resampling to {target_frame_rate}Hz.")
            audio = audio.set_frame_rate(target_frame_rate)
            needs_resave = True
        
        if needs_resave:
            api_logger.info(f"[{request_id}] Re-saving WAV file with standardized format (mono, {target_frame_rate}Hz).")
            audio.export(downloaded_audio_path, format="wav")
            api_logger.info(f"[{request_id}] WAV file standardized and re-saved.")
        else:
            api_logger.info(f"[{request_id}] WAV file already in desired format (mono, {target_frame_rate}Hz or close enough).")

        video_title = info_dict.get('title', 'youtube_video')
        api_logger.info(f"[{request_id}] Successfully processed video: {video_title}")
        
        return jsonify({
            "message": "Audio downloaded and converted to WAV successfully",
            "server_file_path": str(downloaded_audio_path),
            "file_name": downloaded_audio_path.name,
            "original_video_title": video_title
        }), 200

    except yt_dlp.utils.DownloadError as e:
        api_logger.error(f"[{request_id}] yt-dlp DownloadError for URL {youtube_url}: {e}", exc_info=True)
        cleanup_files(downloaded_audio_path)
        return jsonify({"error": f"Failed to download audio from YouTube: {str(e)}"}), 500
    except FileNotFoundError as e: 
        if 'ffmpeg' in str(e).lower() or 'avconv' in str(e).lower():
            api_logger.error(f"[{request_id}] pydub FileNotFoundError: FFmpeg (or AVconv) not found by pydub. Ensure it's installed and in your system PATH. Error: {e}", exc_info=True)
            cleanup_files(downloaded_audio_path)
            return jsonify({"error": "Audio conversion/verification failed: FFmpeg not found by pydub on server."}), 500
        else:
            api_logger.error(f"[{request_id}] FileNotFoundError during processing: {e}", exc_info=True)
            cleanup_files(downloaded_audio_path)
            return jsonify({"error": f"A required file was not found: {str(e)}"}), 500
    except Exception as e:
        api_logger.error(f"[{request_id}] General error processing YouTube URL {youtube_url}: {e}", exc_info=True)
        cleanup_files(downloaded_audio_path)
        return jsonify({"error": f"An internal server error occurred: {str(e)}"}), 500


@app.route('/api/diarize', methods=['POST'])
def diarize_audio_route():
    api_logger.info("Received request to /api/diarize")
    
    audio_to_process_path = None
    original_filename_for_output = "diarized_output" 
    request_id = str(uuid.uuid4()) 
    api_logger.info(f"Diarization request ID: {request_id}")
    
    if 'audio_file' in request.files:
        api_logger.info(f"[{request_id}] Processing uploaded audio file.")
        file = request.files['audio_file']
        if file.filename == '':
            api_logger.warning(f"[{request_id}] No selected file for upload.")
            return jsonify({"error": "No selected file for upload"}), 400
        if file and file.filename.endswith('.wav'):
            temp_audio_filename = f"{request_id}_{file.filename}"
            audio_to_process_path = UPLOAD_FOLDER / temp_audio_filename
            file.save(audio_to_process_path)
            original_filename_for_output = file.filename
            api_logger.info(f"[{request_id}] Uploaded file saved to: {audio_to_process_path}")
        else:
            api_logger.warning(f"[{request_id}] Invalid file type for upload: {file.filename}")
            return jsonify({"error": "Invalid file type for upload. Please upload a .wav file"}), 400
    else:
        data = request.get_json()
        if data and 'server_file_path' in data:
            server_file_path_str = data['server_file_path']
            api_logger.info(f"[{request_id}] Processing server-side audio file: {server_file_path_str}")
            prospective_path = Path(server_file_path_str).resolve()
            
            allowed_parent_dirs = [YOUTUBE_DOWNLOADS_FOLDER.resolve(), UPLOAD_FOLDER.resolve()]
            is_allowed_path = False
            for allowed_dir in allowed_parent_dirs:
                try: 
                    if prospective_path.is_relative_to(allowed_dir):
                        is_allowed_path = True
                        break
                except ValueError: 
                    if str(prospective_path).startswith(str(allowed_dir)):
                        is_allowed_path = True
                        break
                    
            if not (prospective_path.is_file() and is_allowed_path):
                api_logger.error(f"[{request_id}] Invalid or unauthorized server_file_path: {server_file_path_str}. Resolved: {prospective_path}. Allowed: {allowed_parent_dirs}")
                return jsonify({"error": "Invalid server file path provided."}), 400
            audio_to_process_path = prospective_path
            original_filename_for_output = prospective_path.name
        else:
            api_logger.warning(f"[{request_id}] No audio_file uploaded and no server_file_path provided.")
            return jsonify({"error": "No audio_file uploaded and no server_file_path provided."}), 400

    if not audio_to_process_path:
         api_logger.error(f"[{request_id}] Could not determine audio source for diarization.")
         return jsonify({"error": "Could not determine audio source."}), 500

    try:
        request_output_dir = RESULTS_FOLDER / request_id
        request_output_dir.mkdir(parents=True, exist_ok=True)
        api_logger.info(f"[{request_id}] Diarization results for this request will be in: {request_output_dir}")

        config = DiarizationConfig(
            audio_file_path=audio_to_process_path,
            output_dir=request_output_dir,
            force_recompute_asr=True, 
            force_recompute_diarization=True 
        )
        
        api_logger.info(f"[{request_id}] Initializing SpeechDiarizationPipeline for {audio_to_process_path}")
        pipeline = SpeechDiarizationPipeline(config)
        
        api_logger.info(f"[{request_id}] Running diarization pipeline...")
        transcript_segments = pipeline.run() 
        api_logger.info(f"[{request_id}] Diarization pipeline finished.")

        if transcript_segments is None:
            api_logger.error(f"[{request_id}] Diarization pipeline returned None (critical failure).")
            return jsonify({"error": "Diarization process failed critically on the server."}), 500
        
        api_logger.info(f"[{request_id}] Successfully processed. Found {len(transcript_segments)} segments.")
        
        if 'audio_file' in request.files and audio_to_process_path.is_relative_to(UPLOAD_FOLDER.resolve()):
            cleanup_files(audio_to_process_path)
        
        return jsonify({
            "message": "Diarization successful",
            "transcript": transcript_segments,
            "fileName": original_filename_for_output
        }), 200

    except Exception as e:
        api_logger.error(f"[{request_id}] Error during diarization: {e}", exc_info=True)
        if 'audio_file' in request.files and audio_to_process_path and audio_to_process_path.is_relative_to(UPLOAD_FOLDER.resolve()):
            cleanup_files(audio_to_process_path)
        return jsonify({"error": f"An internal server error occurred: {str(e)}"}), 500

if __name__ == '__main__':
    app.run(debug=True, port=5000)

# backend/api.py
import os
import uuid
import logging
from pathlib import Path
from flask import Flask, request, jsonify, send_from_directory # Added send_from_directory
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
CORS(app) # This enables CORS for all routes

BACKEND_DIR = Path(__file__).resolve().parent
UPLOAD_FOLDER = BACKEND_DIR / 'uploads'
YOUTUBE_DOWNLOADS_FOLDER = BACKEND_DIR / 'youtube_downloads' # For both audio and video
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

@app.route('/api/download_youtube_audio', methods=['POST']) # Renaming to reflect it gets audio for diarization
def download_youtube_data_route():
    api_logger.info("Received request to /api/download_youtube_audio (for video and audio)")
    data = request.get_json()
    if not data or 'youtube_url' not in data:
        api_logger.warning("Missing youtube_url in request body")
        return jsonify({"error": "Missing youtube_url in request body"}), 400

    youtube_url = data['youtube_url']
    request_id = str(uuid.uuid4())
    api_logger.info(f"Processing request ID: {request_id} for URL: {youtube_url}")
    
    # Paths for video (mp4) and audio (wav)
    video_filename_mp4 = f"{request_id}.mp4"
    downloaded_video_path_mp4 = YOUTUBE_DOWNLOADS_FOLDER / video_filename_mp4
    
    audio_filename_wav = f"{request_id}.wav" # This will be the audio for diarization
    processed_audio_path_wav = YOUTUBE_DOWNLOADS_FOLDER / audio_filename_wav
    
    temp_downloaded_audio_ext = None # To store extension of initially downloaded audio by yt-dlp

    try:
        api_logger.info(f"[{request_id}] Setting yt-dlp options to download video and extract audio...")
        
        # First, download the video (e.g., best quality MP4)
        ydl_video_opts = {
            'format': 'bestvideo[ext=mp4]+bestaudio[ext=m4a]/best[ext=mp4]/best', # Prioritize MP4
            'outtmpl': str(YOUTUBE_DOWNLOADS_FOLDER / f"{request_id}.%(ext)s"), # Let yt-dlp determine extension initially for video
            'noplaylist': True,
            'quiet': True,
            'verbose': False,
            'nocheckcertificate': True,
            'ffmpeg_location': os.getenv('FFMPEG_PATH'),
            'progress_hooks': [lambda d: api_logger.info(f"[{request_id}] yt-dlp video: {d['status']} - {d.get('_percent_str','')} {d.get('_eta_str','')}") if d['status'] == 'downloading' and '_percent_str' in d else (api_logger.info(f"[{request_id}] yt-dlp video: {d['status']}") if d['status'] == 'finished' else None)],
        }
        
        downloaded_video_actual_path = None
        with yt_dlp.YoutubeDL(ydl_video_opts) as ydl:
            api_logger.info(f"[{request_id}] Starting video download from: {youtube_url}")
            info_dict = ydl.extract_info(youtube_url, download=True)
            # Try to get the actual path of the downloaded video file
            if 'requested_downloads' in info_dict and info_dict['requested_downloads']:
                 downloaded_video_actual_path = Path(info_dict['requested_downloads'][0]['filepath'])
            elif 'filename' in info_dict: # Older yt-dlp versions might put it here directly
                 downloaded_video_actual_path = YOUTUBE_DOWNLOADS_FOLDER / Path(info_dict['filename']).name
            else: # Fallback: try to find it by request_id and common video extensions
                for ext in ['mp4', 'mkv', 'webm']:
                    potential_path = YOUTUBE_DOWNLOADS_FOLDER / f"{request_id}.{ext}"
                    if potential_path.exists():
                        downloaded_video_actual_path = potential_path
                        break
            
            if not downloaded_video_actual_path or not downloaded_video_actual_path.exists():
                api_logger.error(f"[{request_id}] Could not find downloaded video file.")
                return jsonify({"error": "Failed to locate downloaded video file."}), 500
            
            # Rename to consistent .mp4 if it's not already (yt-dlp might choose .mkv or .webm)
            if downloaded_video_actual_path.suffix.lower() != ".mp4":
                api_logger.info(f"[{request_id}] Renaming downloaded video {downloaded_video_actual_path.name} to {video_filename_mp4}")
                downloaded_video_actual_path.rename(downloaded_video_path_mp4)
            else:
                # If it's already mp4 and named with request_id, it's fine.
                # If it's mp4 but has a different name (e.g. video title), rename it.
                if downloaded_video_actual_path.name != video_filename_mp4:
                     downloaded_video_actual_path.rename(downloaded_video_path_mp4)

            api_logger.info(f"[{request_id}] Video downloaded successfully: {downloaded_video_path_mp4}")

        # Now, extract audio from the downloaded video and convert to WAV for diarization
        api_logger.info(f"[{request_id}] Extracting audio from {downloaded_video_path_mp4} to {processed_audio_path_wav}")
        try:
            video_audio = AudioSegment.from_file(str(downloaded_video_path_mp4)) # Load audio from the video
            
            # Standardize audio for diarization pipeline
            if video_audio.channels > 1:
                api_logger.info(f"[{request_id}] Audio from video has {video_audio.channels} channels. Converting to mono.")
                video_audio = video_audio.set_channels(1)
            
            target_frame_rate = 16000
            if video_audio.frame_rate != target_frame_rate:
                api_logger.info(f"[{request_id}] Audio from video frame rate is {video_audio.frame_rate}Hz. Resampling to {target_frame_rate}Hz.")
                video_audio = video_audio.set_frame_rate(target_frame_rate)
            
            video_audio.export(processed_audio_path_wav, format="wav")
            api_logger.info(f"[{request_id}] Audio extracted and saved as WAV: {processed_audio_path_wav}")
        except Exception as e_audio_extract:
            api_logger.error(f"[{request_id}] Failed to extract or convert audio from video: {e_audio_extract}", exc_info=True)
            cleanup_files(downloaded_video_path_mp4) # Clean up video if audio extraction failed
            return jsonify({"error": "Failed to extract audio from video for diarization."}), 500

        video_title = info_dict.get('title', 'youtube_video')
        api_logger.info(f"[{request_id}] Successfully processed video: {video_title}")
        
        return jsonify({
            "message": "Video downloaded and audio extracted successfully",
            "video_file_url": f"/api/video/{video_filename_mp4}", # URL to stream/fetch the video
            "audio_server_file_path": str(processed_audio_path_wav), # Path to WAV audio for diarization
            "audio_file_name": audio_filename_wav, # Name of the WAV file
            "original_video_title": video_title
        }), 200

    except yt_dlp.utils.DownloadError as e:
        api_logger.error(f"[{request_id}] yt-dlp DownloadError for URL {youtube_url}: {e}", exc_info=True)
        cleanup_files(downloaded_video_path_mp4, processed_audio_path_wav)
        return jsonify({"error": f"Failed to download video from YouTube: {str(e)}"}), 500
    except FileNotFoundError as e: 
        if 'ffmpeg' in str(e).lower() or 'avconv' in str(e).lower():
            api_logger.error(f"[{request_id}] pydub/yt-dlp FileNotFoundError: FFmpeg not found. Error: {e}", exc_info=True)
            cleanup_files(downloaded_video_path_mp4, processed_audio_path_wav)
            return jsonify({"error": "Processing failed: FFmpeg not found on server."}), 500
        else:
            api_logger.error(f"[{request_id}] FileNotFoundError during processing: {e}", exc_info=True)
            cleanup_files(downloaded_video_path_mp4, processed_audio_path_wav)
            return jsonify({"error": f"A required file was not found: {str(e)}"}), 500
    except Exception as e:
        api_logger.error(f"[{request_id}] General error processing YouTube URL {youtube_url}: {e}", exc_info=True)
        cleanup_files(downloaded_video_path_mp4, processed_audio_path_wav)
        return jsonify({"error": f"An internal server error occurred: {str(e)}"}), 500

# New route to serve video files
@app.route('/api/video/<filename>')
def serve_video(filename):
    api_logger.info(f"Request to serve video: {filename}")
    # Basic security: ensure filename is somewhat safe (e.g., doesn't contain '..')
    if '..' in filename or filename.startswith('/'):
        api_logger.warning(f"Attempt to access potentially unsafe path: {filename}")
        return "Invalid filename", 400
    
    # Ensure the file being requested is within the YOUTUBE_DOWNLOADS_FOLDER
    file_path = (YOUTUBE_DOWNLOADS_FOLDER / filename).resolve()
    if not file_path.is_file() or not file_path.is_relative_to(YOUTUBE_DOWNLOADS_FOLDER.resolve()):
        api_logger.error(f"Video file not found or access denied: {file_path}")
        return "File not found", 404
        
    return send_from_directory(YOUTUBE_DOWNLOADS_FOLDER, filename, as_attachment=False)


# /api/diarize route remains largely the same, but ensure it can handle server_file_path
# from YOUTUBE_DOWNLOADS_FOLDER correctly. (The existing logic should be fine)
@app.route('/api/diarize', methods=['POST'])
def diarize_audio_route():
    api_logger.info("Received request to /api/diarize")
    
    audio_to_process_path = None
    original_filename_for_output = "diarized_output" 
    request_id = str(uuid.uuid4()) 
    api_logger.info(f"Diarization request ID: {request_id}")
    
    if 'audio_file' in request.files:
        # ... (existing file upload logic remains the same) ...
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
        if data and 'server_file_path' in data: # Changed from audio_server_file_path for consistency
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
        
        # Clean up uploaded file if it was a direct upload and temporary
        if 'audio_file' in request.files and audio_to_process_path.is_relative_to(UPLOAD_FOLDER.resolve()):
            cleanup_files(audio_to_process_path)
        # Note: The WAV extracted from YouTube is kept in YOUTUBE_DOWNLOADS_FOLDER for now.
        # The MP4 video is also kept. Consider a cleanup strategy for these.
        
        return jsonify({
            "message": "Diarization successful",
            "transcript": transcript_segments,
            "fileName": original_filename_for_output # This will be the .wav name for YouTube audio
        }), 200

    except Exception as e:
        api_logger.error(f"[{request_id}] Error during diarization: {e}", exc_info=True)
        if 'audio_file' in request.files and audio_to_process_path and audio_to_process_path.is_relative_to(UPLOAD_FOLDER.resolve()):
            cleanup_files(audio_to_process_path)
        return jsonify({"error": f"An internal server error occurred: {str(e)}"}), 500

if __name__ == '__main__':
    app.run(debug=True, port=5000)

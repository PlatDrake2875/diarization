# backend/api.py
import os
import uuid
import logging
from pathlib import Path
from flask import Flask, request, jsonify
from flask_cors import CORS

# Assuming your existing diarization logic is in these files
# Adjust imports based on your actual backend structure if needed
from config import DiarizationConfig
from pipeline_core import SpeechDiarizationPipeline

# --- Setup Logging ---
# Configure logging for the API
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    datefmt='%Y-%m-%d %H:%M:%S'
)
api_logger = logging.getLogger(__name__)

app = Flask(__name__)
CORS(app)  # Enable CORS for all routes, allowing requests from your frontend

# Define upload and results directories within the backend
# Ensure these directories exist or are created
BACKEND_DIR = Path(__file__).resolve().parent
UPLOAD_FOLDER = BACKEND_DIR / 'uploads'
RESULTS_FOLDER = BACKEND_DIR / 'diarization_results'
UPLOAD_FOLDER.mkdir(parents=True, exist_ok=True)
RESULTS_FOLDER.mkdir(parents=True, exist_ok=True)

# Helper function to parse the transcript text file into JSON
# This is needed if pipeline.run() doesn't directly return the structured list
# or if you want to re-parse from a file.
# However, your current pipeline_core.run() *does* return the structured list,
# so this helper might only be for fallback or if you change that.
def parse_transcript_file(file_path: Path) -> list:
    """
    Parses a .txt transcript file into a list of segment objects.
    Assumes format: [SPEAKER_ID] (start_time_s - end_time_s): text
    """
    segments = []
    try:
        with open(file_path, 'r', encoding='utf-8') as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    # Example parsing, adjust regex if format is more complex
                    # [SPEAKER_XX] (0.00s - 1.23s): Hello world
                    speaker_part, rest = line.split(']', 1)
                    speaker = speaker_part[1:] # Remove '['

                    time_part, text_part = rest.split('):', 1)
                    time_values = time_part.replace('(', '').replace('s', '').split(' - ')
                    
                    start_time = float(time_values[0])
                    end_time = float(time_values[1])
                    text = text_part.strip()
                    
                    segments.append({
                        "speaker": speaker,
                        "start_time": start_time,
                        "end_time": end_time,
                        "text": text
                    })
                except ValueError as ve:
                    api_logger.warning(f"Skipping malformed line in transcript '{file_path}': {line} - Error: {ve}")
                except Exception as e:
                    api_logger.warning(f"Error parsing line '{line}' in transcript '{file_path}': {e}")
        return segments
    except FileNotFoundError:
        api_logger.error(f"Transcript file not found for parsing: {file_path}")
        return []
    except Exception as e:
        api_logger.error(f"Failed to read or parse transcript file {file_path}: {e}")
        return []


@app.route('/api/diarize', methods=['POST'])
def diarize_audio_route():
    api_logger.info("Received request to /api/diarize")
    if 'audio_file' not in request.files:
        api_logger.warning("No audio_file part in request")
        return jsonify({"error": "No audio_file part in the request"}), 400

    file = request.files['audio_file']

    if file.filename == '':
        api_logger.warning("No selected file")
        return jsonify({"error": "No selected file"}), 400

    if file and file.filename.endswith('.wav'):
        try:
            # Create a unique ID for this request to manage files
            request_id = str(uuid.uuid4())
            
            # Save the uploaded file temporarily
            temp_audio_filename = f"{request_id}_{file.filename}"
            temp_audio_path = UPLOAD_FOLDER / temp_audio_filename
            file.save(temp_audio_path)
            api_logger.info(f"Uploaded file saved to: {temp_audio_path}")

            # Configure output directory for this specific request
            # This helps keep results organized if multiple requests occur
            # and makes cleanup easier.
            request_output_dir = RESULTS_FOLDER / request_id
            request_output_dir.mkdir(parents=True, exist_ok=True)
            api_logger.info(f"Results for this request will be in: {request_output_dir}")

            # --- Configure and Run the Diarization Pipeline ---
            # Use your existing DiarizationConfig and SpeechDiarizationPipeline
            # Note: You might want to adjust some config parameters based on API needs
            # For example, force_recompute could be false to leverage caching for repeated files if desired,
            # or true to always reprocess.
            config = DiarizationConfig(
                audio_file_path=temp_audio_path,
                output_dir=request_output_dir,
                # hf_access_token can be read from env or passed if needed
                # device can be auto-detected or configured
                force_recompute_asr=True, # Or False, depending on desired caching behavior
                force_recompute_diarization=True 
            )
            
            api_logger.info(f"Initializing SpeechDiarizationPipeline for {temp_audio_path}")
            pipeline = SpeechDiarizationPipeline(config)
            
            api_logger.info("Running diarization pipeline...")
            # The run() method should return the list of segments directly
            transcript_segments = pipeline.run() 
            api_logger.info("Diarization pipeline finished.")

            if transcript_segments is None:
                # This means the pipeline itself indicated a critical failure
                api_logger.error("Diarization pipeline returned None (critical failure).")
                return jsonify({"error": "Diarization process failed critically on the server."}), 500
            
            # The pipeline's run() method returns the structured transcript
            # So, we don't necessarily need to parse the .txt file here unless it's a fallback
            # or if run() only saves the file.
            # Assuming run() returns the list of dicts:
            
            api_logger.info(f"Successfully processed. Found {len(transcript_segments)} segments.")
            
            # --- Cleanup (Optional but Recommended) ---
            # You might want to clean up the uploaded file and its specific results dir
            # after sending the response, or have a separate cleanup job.
            # For simplicity here, we'll leave them, but in production, manage this.
            # Example cleanup:
            # temp_audio_path.unlink(missing_ok=True)
            # import shutil
            # shutil.rmtree(request_output_dir, ignore_errors=True)
            # api_logger.info(f"Cleaned up temporary files for request {request_id}")

            return jsonify({
                "message": "Diarization successful",
                "transcript": transcript_segments,
                "fileName": file.filename # Send original filename back for context
            }), 200

        except Exception as e:
            api_logger.error(f"Error during diarization: {e}", exc_info=True)
            # Also remove temporary file if an error occurs mid-process
            if 'temp_audio_path' in locals() and temp_audio_path.exists():
                temp_audio_path.unlink(missing_ok=True)
            if 'request_output_dir' in locals() and request_output_dir.exists():
                import shutil
                shutil.rmtree(request_output_dir, ignore_errors=True)

            return jsonify({"error": f"An internal server error occurred: {str(e)}"}), 500
    else:
        api_logger.warning(f"Invalid file type: {file.filename}")
        return jsonify({"error": "Invalid file type. Please upload a .wav file"}), 400

if __name__ == '__main__':
    # Make sure to run this from the 'Speaker Diarization' root directory
    # or adjust paths if running directly from 'backend'
    # Example: python backend/api.py
    app.run(debug=True, port=5000) # Runs on http://localhost:5000

// frontend/src/components/YouTubeDiarizationPage/YouTubeDiarizationPage.jsx
import React, { useState, useEffect, useRef } from 'react';
import axios from 'axios';
import TranscriptEditor from '../TranscriptEditor/TranscriptEditor'; // Adjust path if needed
import styles from './YouTubeDiarizationPage.module.css';

function YouTubeDiarizationPage() {
  const [youtubeUrl, setYoutubeUrl] = useState('');
  const [videoId, setVideoId] = useState(''); // To extract video ID for embed

  const [isDownloading, setIsDownloading] = useState(false);
  const [downloadError, setDownloadError] = useState('');
  const [downloadSuccessMessage, setDownloadSuccessMessage] = useState('');
  
  const [serverFilePath, setServerFilePath] = useState(''); // Path of .wav on server
  const [downloadedFileName, setDownloadedFileName] = useState(''); // Name of the .wav file
  const [originalVideoTitle, setOriginalVideoTitle] = useState('');

  // Diarization states (similar to DiarizationPage)
  const [transcript, setTranscript] = useState(null);
  const [isDiarizing, setIsDiarizing] = useState(false);
  const [diarizationError, setDiarizationError] = useState('');
  
  const [startTime, setStartTime] = useState(null);
  const [elapsedTime, setElapsedTime] = useState(0);
  const timerIntervalRef = useRef(null);

  useEffect(() => {
    if ((isDownloading || isDiarizing) && startTime) {
      timerIntervalRef.current = setInterval(() => {
        setElapsedTime(Math.floor((Date.now() - startTime) / 1000));
      }, 1000);
    } else {
      clearInterval(timerIntervalRef.current);
    }
    return () => clearInterval(timerIntervalRef.current);
  }, [isDownloading, isDiarizing, startTime]);

  const extractVideoID = (url) => {
    const regExp = /^.*(youtu.be\/|v\/|u\/\w\/|embed\/|watch\?v=|&v=)([^#&?]*).*/;
    const match = url.match(regExp);
    return (match && match[2].length === 11) ? match[2] : null;
  };

  const handleUrlChange = (e) => {
    const newUrl = e.target.value;
    setYoutubeUrl(newUrl);
    const id = extractVideoID(newUrl);
    setVideoId(id);
    // Clear previous download/diarization states when URL changes
    setDownloadError('');
    setDownloadSuccessMessage('');
    setServerFilePath('');
    setDownloadedFileName('');
    setTranscript(null);
    setDiarizationError('');
  };

  const handleDownloadAudio = async () => {
    if (!youtubeUrl) {
      setDownloadError("Please enter a YouTube URL.");
      return;
    }
    if (!videoId) {
        setDownloadError("Invalid YouTube URL. Could not extract video ID.");
        return;
    }

    setIsDownloading(true);
    setDownloadError('');
    setDownloadSuccessMessage('');
    setServerFilePath('');
    setTranscript(null); // Clear previous transcript
    setDiarizationError('');
    setStartTime(Date.now());
    setElapsedTime(0);

    try {
      const response = await axios.post('http://localhost:5000/api/download_youtube_audio', { 
        youtube_url: youtubeUrl 
      });
      setDownloadSuccessMessage(`Audio '${response.data.original_video_title}' downloaded and converted!`);
      setServerFilePath(response.data.server_file_path);
      setDownloadedFileName(response.data.file_name);
      setOriginalVideoTitle(response.data.original_video_title);
    } catch (err) {
      console.error("Download error details:", err);
      let msg = "Failed to download or convert audio. ";
      if (err.response) {
        msg += `Server: ${err.response.data?.error || 'Unknown server error.'}`;
      } else {
        msg += `Network error or server unreachable.`;
      }
      setDownloadError(msg);
    } finally {
      setIsDownloading(false);
      // Elapsed time will stop updating via useEffect
    }
  };

  const handleDiarizeDownloadedAudio = async () => {
    if (!serverFilePath) {
      setDiarizationError("No downloaded audio file path available to diarize.");
      return;
    }
    setIsDiarizing(true);
    setDiarizationError('');
    setTranscript(null);
    setStartTime(Date.now()); // Reset start time for diarization phase
    setElapsedTime(0);

    try {
      const response = await axios.post('http://localhost:5000/api/diarize', {
        server_file_path: serverFilePath // Send the server path
      });
      setTranscript(response.data.transcript);
    } catch (err) {
      console.error("Diarization error details:", err);
      let msg = "Diarization failed. ";
      if (err.response) {
        msg += `Server: ${err.response.data?.error || 'Unknown server error.'}`;
      } else {
        msg += `Network error or server unreachable.`;
      }
      setDiarizationError(msg);
    } finally {
      setIsDiarizing(false);
    }
  };
  
  const handleTranscriptSegmentsChange = (updatedSegments) => {
    setTranscript(updatedSegments);
  };

  const formatElapsedTime = (seconds) => {
    const mins = Math.floor(seconds / 60);
    const secs = seconds % 60;
    return `${String(mins).padStart(2, '0')}:${String(secs).padStart(2, '0')}`;
  };

  return (
    <div className={styles.ytPageContainer}>
      <header className={styles.pageHeader}>
        <h2>Diarize from YouTube</h2>
        <p>Enter a YouTube video link to download its audio and diarize.</p>
      </header>

      <div className={styles.inputSection}>
        <input
          type="text"
          className={styles.urlInput}
          value={youtubeUrl}
          onChange={handleUrlChange}
          placeholder="Enter YouTube Video URL (e.g., https://www.youtube.com/watch?v=...)"
        />
        <button 
          onClick={handleDownloadAudio} 
          disabled={isDownloading || !youtubeUrl || !videoId}
          className={styles.actionButton}
        >
          {isDownloading ? 'Downloading...' : 'Fetch & Download Audio'}
        </button>
      </div>

      {videoId && (
        <div className={styles.videoPreview}>
          <iframe
            width="560"
            height="315"
            src={`https://www.youtube.com/embed/${videoId}`}
            title="YouTube video player"
            frameBorder="0"
            allow="accelerometer; autoplay; clipboard-write; encrypted-media; gyroscope; picture-in-picture"
            allowFullScreen
          ></iframe>
        </div>
      )}

      {(isDownloading || isDiarizing) && (
        <div className={styles.loadingContainer}>
          <div className={styles.hourglass}>⏳</div>
          <p>{isDownloading ? 'Downloading and converting audio...' : 'Diarizing audio...'}</p>
          <p className={styles.elapsedTime}>
            Time Elapsed: {formatElapsedTime(elapsedTime)}
          </p>
        </div>
      )}

      {downloadError && !isDownloading && (
        <div className={styles.errorContainer}>
          <p className={styles.errorMessage}>{downloadError}</p>
        </div>
      )}
      {downloadSuccessMessage && !isDownloading && !serverFilePath && ( // Show only if not yet ready to diarize
         <div className={styles.successContainer}>
            <p className={styles.successMessage}>{downloadSuccessMessage}</p>
         </div>
      )}


      {serverFilePath && !isDownloading && !isDiarizing && (
        <div className={styles.diarizeActionSection}>
          <p className={styles.readyMessage}>
            Audio for "<strong>{originalVideoTitle || downloadedFileName}</strong>" is ready.
          </p>
          <button 
            onClick={handleDiarizeDownloadedAudio} 
            className={styles.actionButton}
            disabled={isDiarizing}
          >
            {isDiarizing ? 'Diarizing...' : 'Diarize This Audio'}
          </button>
        </div>
      )}

      {diarizationError && !isDiarizing && (
         <div className={styles.errorContainer}>
            <p className={styles.errorMessage}>{diarizationError}</p>
         </div>
      )}

      {transcript && !isDiarizing && !diarizationError && (
        <TranscriptEditor
          key={downloadedFileName} 
          initialTranscript={transcript}
          onTranscriptChange={handleTranscriptSegmentsChange}
          fileName={downloadedFileName || 'YouTube Audio'}
        />
      )}
    </div>
  );
}

export default YouTubeDiarizationPage;

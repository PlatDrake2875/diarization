// frontend/src/components/YouTubeDiarizationPage/YouTubeDiarizationPage.jsx
import React, { useState, useEffect, useRef } from 'react';
import axios from 'axios';
import TranscriptEditor from '../TranscriptEditor/TranscriptEditor';
import styles from './YouTubeDiarizationPage.module.css';

function YouTubeDiarizationPage() {
  const [youtubeUrl, setYoutubeUrl] = useState('');
  const [videoId, setVideoId] = useState('');

  const [isDownloading, setIsDownloading] = useState(false);
  const [downloadError, setDownloadError] = useState('');
  const [downloadSuccessMessage, setDownloadSuccessMessage] = useState('');
  const [downloadDuration, setDownloadDuration] = useState(null);
  
  const [serverFilePath, setServerFilePath] = useState('');
  const [downloadedFileName, setDownloadedFileName] = useState('');
  const [originalVideoTitle, setOriginalVideoTitle] = useState('');

  const [transcript, setTranscript] = useState(null);
  const [isDiarizing, setIsDiarizing] = useState(false);
  const [diarizationError, setDiarizationError] = useState('');
  const [diarizationDuration, setDiarizationDuration] = useState(null);
  
  // Renamed operationStartTime to currentOperationStartTimeRef to avoid confusion with state
  // This ref will hold the start time for the *current* in-progress operation.
  const currentOperationStartTimeRef = useRef(null); 
  const [elapsedTime, setElapsedTime] = useState(0);
  const timerIntervalRef = useRef(null);

  useEffect(() => {
    if ((isDownloading || isDiarizing) && currentOperationStartTimeRef.current) {
      timerIntervalRef.current = setInterval(() => {
        setElapsedTime(Math.floor((Date.now() - currentOperationStartTimeRef.current) / 1000));
      }, 1000);
    } else {
      clearInterval(timerIntervalRef.current);
    }
    return () => clearInterval(timerIntervalRef.current);
  }, [isDownloading, isDiarizing]); // Depend only on loading states

  const extractVideoID = (url) => {
    const regExp = /^.*(http:\/\/googleusercontent.com\/youtube.com\/0\/|v\/|u\/\w\/|embed\/|watch\?v=|&v=)([^#&?]*).*/;
    const match = url.match(regExp);
    return (match && match[2].length === 11) ? match[2] : null;
  };

  const handleUrlChange = (e) => {
    const newUrl = e.target.value;
    setYoutubeUrl(newUrl);
    const id = extractVideoID(newUrl);
    setVideoId(id);
    setDownloadError('');
    setDownloadSuccessMessage('');
    setServerFilePath('');
    setDownloadedFileName('');
    setTranscript(null);
    setDiarizationError('');
    setDownloadDuration(null);
    setDiarizationDuration(null);
    setElapsedTime(0); 
    currentOperationStartTimeRef.current = null; // Reset ref
  };

  const formatElapsedTime = (seconds) => {
    if (seconds === null || seconds === undefined) return '00:00';
    const mins = Math.floor(seconds / 60);
    const secs = seconds % 60;
    return `${String(mins).padStart(2, '0')}:${String(secs).padStart(2, '0')}`;
  };

  const handleDownloadAudio = async () => {
    if (!youtubeUrl || !videoId) {
      setDownloadError(!youtubeUrl ? "Please enter a YouTube URL." : "Invalid YouTube URL. Could not extract video ID.");
      return;
    }
    
    const localStartTime = Date.now(); // Capture start time locally
    currentOperationStartTimeRef.current = localStartTime; // Set ref for live timer

    setIsDownloading(true);
    setDownloadError('');
    setDownloadSuccessMessage('');
    setServerFilePath('');
    setTranscript(null);
    setDiarizationError('');
    setDownloadDuration(null);
    setDiarizationDuration(null);
    setElapsedTime(0);

    try {
      const response = await axios.post('http://localhost:5000/api/download_youtube_audio', { 
        youtube_url: youtubeUrl 
      });
      const duration = Math.floor((Date.now() - localStartTime) / 1000); // Use localStartTime
      setDownloadDuration(duration);
      setDownloadSuccessMessage(`Audio for "${response.data.original_video_title}" downloaded!`);
      setServerFilePath(response.data.server_file_path);
      setDownloadedFileName(response.data.file_name);
      setOriginalVideoTitle(response.data.original_video_title);
    } catch (err) {
      const duration = Math.floor((Date.now() - localStartTime) / 1000); // Use localStartTime
      setDownloadDuration(duration);
      console.error("Download error details:", err);
      let msg = "Failed to download or convert audio. ";
      if (err.response) msg += `Server: ${err.response.data?.error || 'Unknown server error.'}`;
      else msg += `Network error or server unreachable.`;
      setDownloadError(msg);
    } finally {
      setIsDownloading(false);
      currentOperationStartTimeRef.current = null; // Clear ref after operation
    }
  };

  const handleDiarizeDownloadedAudio = async () => {
    if (!serverFilePath) {
      setDiarizationError("No downloaded audio file path available to diarize.");
      return;
    }

    const localStartTime = Date.now(); // Capture start time locally
    currentOperationStartTimeRef.current = localStartTime; // Set ref for live timer

    setIsDiarizing(true);
    setDiarizationError('');
    setTranscript(null);
    setDiarizationDuration(null);
    setElapsedTime(0);

    try {
      const response = await axios.post('http://localhost:5000/api/diarize', {
        server_file_path: serverFilePath
      });
      const duration = Math.floor((Date.now() - localStartTime) / 1000); // Use localStartTime
      setDiarizationDuration(duration);
      setTranscript(response.data.transcript);
    } catch (err) {
      const duration = Math.floor((Date.now() - localStartTime) / 1000); // Use localStartTime
      setDiarizationDuration(duration);
      console.error("Diarization error details:", err);
      let msg = "Diarization failed. ";
      if (err.response) msg += `Server: ${err.response.data?.error || 'Unknown server error.'}`;
      else msg += `Network error or server unreachable.`;
      setDiarizationError(msg);
    } finally {
      setIsDiarizing(false);
      currentOperationStartTimeRef.current = null; // Clear ref after operation
    }
  };
  
  const handleTranscriptSegmentsChange = (updatedSegments) => {
    setTranscript(updatedSegments);
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
          placeholder="Enter YouTube Video URL"
          disabled={isDownloading || isDiarizing}
        />
        <button 
          onClick={handleDownloadAudio} 
          disabled={isDownloading || isDiarizing || !youtubeUrl || !videoId}
          className={styles.actionButton}
        >
          {isDownloading ? 'Downloading...' : 'Fetch & Download Audio'}
        </button>
      </div>

      {videoId && !isDownloading && !serverFilePath && (
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

      {!isDownloading && downloadDuration !== null && (
        <div className={styles.summaryContainer}>
          <p>Download & Conversion Time: {formatElapsedTime(downloadDuration)}</p>
        </div>
      )}
      {downloadError && !isDownloading && (
        <div className={styles.errorContainer}>
          <p className={styles.errorMessage}>{downloadError}</p>
        </div>
      )}
      {downloadSuccessMessage && !isDownloading && serverFilePath && !transcript && !isDiarizing && (
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
      
      {!isDiarizing && diarizationDuration !== null && (
         <div className={styles.summaryContainer}>
            <p>Diarization Time: {formatElapsedTime(diarizationDuration)}</p>
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

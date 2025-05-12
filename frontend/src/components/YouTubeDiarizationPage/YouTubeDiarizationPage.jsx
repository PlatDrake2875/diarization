// frontend/src/components/YouTubeDiarizationPage/YouTubeDiarizationPage.jsx
import React, { useState, useEffect, useRef } from 'react';
import axios from 'axios';
import TranscriptEditor from '../TranscriptEditor/TranscriptEditor';
import SegmentedTrackbar from '../SegmentedTrackbar/SegmentedTrackbar'; // New component
import styles from './YouTubeDiarizationPage.module.css';

function YouTubeDiarizationPage() {
  const [youtubeUrl, setYoutubeUrl] = useState('');
  // const [videoId, setVideoId] = useState(''); // No longer strictly needed for embed if using local player

  const [isDownloading, setIsDownloading] = useState(false);
  const [downloadError, setDownloadError] = useState('');
  const [downloadSuccessMessage, setDownloadSuccessMessage] = useState('');
  const [downloadDuration, setDownloadDuration] = useState(null);
  
  const [videoUrlForPlayer, setVideoUrlForPlayer] = useState(''); // URL for the <video> src
  const [audioServerFilePath, setAudioServerFilePath] = useState(''); // Path of .wav on server for diarization
  const [processedFileName, setProcessedFileName] = useState(''); // Name of the .wav file or original video title
  const [originalVideoTitle, setOriginalVideoTitle] = useState('');

  const [transcript, setTranscript] = useState(null);
  const [isDiarizing, setIsDiarizing] = useState(false);
  const [diarizationError, setDiarizationError] = useState('');
  const [diarizationDuration, setDiarizationDuration] = useState(null);
  
  const currentOperationStartTimeRef = useRef(null); 
  const [elapsedTime, setElapsedTime] = useState(0);
  const timerIntervalRef = useRef(null);
  const videoRef = useRef(null); // Ref for the <video> element
  const [videoDuration, setVideoDuration] = useState(0); // Duration of the video for trackbar

  useEffect(() => {
    if ((isDownloading || isDiarizing) && currentOperationStartTimeRef.current) {
      timerIntervalRef.current = setInterval(() => {
        setElapsedTime(Math.floor((Date.now() - currentOperationStartTimeRef.current) / 1000));
      }, 1000);
    } else {
      clearInterval(timerIntervalRef.current);
    }
    return () => clearInterval(timerIntervalRef.current);
  }, [isDownloading, isDiarizing]);

  const handleUrlChange = (e) => {
    const newUrl = e.target.value;
    setYoutubeUrl(newUrl);
    setVideoUrlForPlayer(''); // Clear video player on new URL
    setDownloadError('');
    setDownloadSuccessMessage('');
    setAudioServerFilePath('');
    setProcessedFileName('');
    setTranscript(null);
    setDiarizationError('');
    setDownloadDuration(null);
    setDiarizationDuration(null);
    setElapsedTime(0); 
    currentOperationStartTimeRef.current = null;
  };

  const formatElapsedTime = (seconds) => {
    if (seconds === null || seconds === undefined) return '00:00';
    const mins = Math.floor(seconds / 60);
    const secs = seconds % 60;
    return `${String(mins).padStart(2, '0')}:${String(secs).padStart(2, '0')}`;
  };

  const handleDownload = async () => {
    if (!youtubeUrl) {
      setDownloadError("Please enter a YouTube URL.");
      return;
    }
    
    const localStartTime = Date.now(); 
    currentOperationStartTimeRef.current = localStartTime;

    setIsDownloading(true);
    setDownloadError('');
    setDownloadSuccessMessage('');
    setAudioServerFilePath('');
    setVideoUrlForPlayer('');
    setTranscript(null);
    setDiarizationError('');
    setDownloadDuration(null);
    setDiarizationDuration(null);
    setElapsedTime(0);

    try {
      const response = await axios.post('http://localhost:5000/api/download_youtube_audio', { 
        youtube_url: youtubeUrl 
      });
      const duration = Math.floor((Date.now() - localStartTime) / 1000);
      setDownloadDuration(duration);
      setDownloadSuccessMessage(`Data for "${response.data.original_video_title}" ready!`);
      setVideoUrlForPlayer(`http://localhost:5000${response.data.video_file_url}`); // Full URL to backend server
      setAudioServerFilePath(response.data.audio_server_file_path);
      setProcessedFileName(response.data.file_name); // This is the .wav filename
      setOriginalVideoTitle(response.data.original_video_title);
    } catch (err) {
      const duration = Math.floor((Date.now() - localStartTime) / 1000);
      setDownloadDuration(duration);
      console.error("Download error details:", err);
      let msg = "Failed to download video/audio. ";
      if (err.response) msg += `Server: ${err.response.data?.error || 'Unknown server error.'}`;
      else msg += `Network error or server unreachable.`;
      setDownloadError(msg);
    } finally {
      setIsDownloading(false);
      currentOperationStartTimeRef.current = null;
    }
  };

  const handleDiarize = async () => {
    if (!audioServerFilePath) {
      setDiarizationError("No downloaded audio available to diarize.");
      return;
    }
    const localStartTime = Date.now();
    currentOperationStartTimeRef.current = localStartTime;

    setIsDiarizing(true);
    setDiarizationError('');
    setTranscript(null); // Clear previous transcript before new diarization
    setDiarizationDuration(null);
    setElapsedTime(0);

    try {
      const response = await axios.post('http://localhost:5000/api/diarize', {
        server_file_path: audioServerFilePath 
      });
      const duration = Math.floor((Date.now() - localStartTime) / 1000);
      setDiarizationDuration(duration);
      setTranscript(response.data.transcript);
    } catch (err) {
      const duration = Math.floor((Date.now() - localStartTime) / 1000);
      setDiarizationDuration(duration);
      console.error("Diarization error details:", err);
      let msg = "Diarization failed. ";
      if (err.response) msg += `Server: ${err.response.data?.error || 'Unknown server error.'}`;
      else msg += `Network error or server unreachable.`;
      setDiarizationError(msg);
    } finally {
      setIsDiarizing(false);
      currentOperationStartTimeRef.current = null;
    }
  };
  
  const handleTranscriptSegmentsChange = (updatedSegments) => {
    setTranscript(updatedSegments);
  };

  const handleVideoLoadedMetadata = () => {
    if (videoRef.current) {
      setVideoDuration(videoRef.current.duration);
    }
  };

  const handleSeekFromTrackbar = (time) => {
    if (videoRef.current) {
      videoRef.current.currentTime = time;
    }
  };


  return (
    <div className={styles.ytPageContainer}>
      <header className={styles.pageHeader}>
        <h2>Diarize from YouTube</h2>
        <p>Enter a YouTube video link, download, and diarize its audio.</p>
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
          onClick={handleDownload} 
          disabled={isDownloading || isDiarizing || !youtubeUrl}
          className={styles.actionButton}
        >
          {isDownloading ? 'Processing...' : 'Fetch Video & Audio'}
        </button>
      </div>

      {(isDownloading || isDiarizing) && (
        <div className={styles.loadingContainer}>
          <div className={styles.hourglass}>⏳</div>
          <p>{isDownloading ? 'Downloading video and extracting audio...' : 'Diarizing audio...'}</p>
          <p className={styles.elapsedTime}>
            Time Elapsed: {formatElapsedTime(elapsedTime)}
          </p>
        </div>
      )}

      {!isDownloading && downloadDuration !== null && (
        <div className={styles.summaryContainer}>
          <p>Video/Audio Fetch Time: {formatElapsedTime(downloadDuration)}</p>
        </div>
      )}
      {downloadError && !isDownloading && (
        <div className={styles.errorContainer}><p className={styles.errorMessage}>{downloadError}</p></div>
      )}
      
      {videoUrlForPlayer && !isDownloading && (
        <div className={styles.videoPlayerSection}>
          <h3>{originalVideoTitle || 'Video Preview'}</h3>
          <video
            ref={videoRef}
            key={videoUrlForPlayer} /* Force re-render if URL changes */
            controls
            width="100%" 
            className={styles.videoPlayer}
            onLoadedMetadata={handleVideoLoadedMetadata}
          >
            <source src={videoUrlForPlayer} type="video/mp4" />
            Your browser does not support the video tag.
          </video>
          {transcript && videoDuration > 0 && (
            <SegmentedTrackbar 
              segments={transcript} 
              duration={videoDuration}
              onSeek={handleSeekFromTrackbar}
            />
          )}
        </div>
      )}

      {audioServerFilePath && !isDownloading && !isDiarizing && (
        <div className={styles.diarizeActionSection}>
          {!transcript && ( // Show diarize button only if no transcript yet for this video
            <button 
              onClick={handleDiarize} 
              className={styles.actionButton}
              disabled={isDiarizing}
            >
              {isDiarizing ? 'Diarizing...' : `Diarize "${originalVideoTitle || 'this video'}"`}
            </button>
          )}
        </div>
      )}
      
      {!isDiarizing && diarizationDuration !== null && (
         <div className={styles.summaryContainer}>
            <p>Diarization Time: {formatElapsedTime(diarizationDuration)}</p>
         </div>
      )}
      {diarizationError && !isDiarizing && (
         <div className={styles.errorContainer}><p className={styles.errorMessage}>{diarizationError}</p></div>
      )}

      {transcript && !isDiarizing && !diarizationError && (
        <TranscriptEditor
          key={processedFileName} 
          initialTranscript={transcript}
          onTranscriptChange={handleTranscriptSegmentsChange}
          fileName={originalVideoTitle || processedFileName || 'YouTube Audio'}
        />
      )}
    </div>
  );
}

export default YouTubeDiarizationPage;

// frontend/src/components/DiarizationPage/DiarizationPage.jsx
import React, { useState, useEffect, useRef } from 'react';
import FileUpload from '../FileUpload/FileUpload'; // Assuming FileUpload is in a subfolder
import TranscriptEditor from '../TranscriptEditor/TranscriptEditor'; // Assuming TranscriptEditor is in a subfolder
import styles from './DiarizationPage.module.css';

function DiarizationPage() {
  const [transcript, setTranscript] = useState(null);
  const [isLoading, setIsLoading] = useState(false);
  const [error, setError] = useState('');
  const [processedFileName, setProcessedFileName] = useState('');
  
  const [startTime, setStartTime] = useState(null);
  const [elapsedTime, setElapsedTime] = useState(0);
  const timerIntervalRef = useRef(null);

  useEffect(() => {
    if (isLoading && startTime) {
      timerIntervalRef.current = setInterval(() => {
        setElapsedTime(Math.floor((Date.now() - startTime) / 1000));
      }, 1000);
    } else {
      clearInterval(timerIntervalRef.current);
    }
    return () => clearInterval(timerIntervalRef.current);
  }, [isLoading, startTime]);

  const handleProcessingStart = () => {
    setIsLoading(true);
    setStartTime(Date.now());
    setElapsedTime(0);
    setError('');
    setTranscript(null);
    setProcessedFileName('');
  };

  const handleDiarizationComplete = (transcriptData, originalFileName) => {
    setTranscript(transcriptData);
    setProcessedFileName(originalFileName);
    setIsLoading(false);
    setError('');
    console.log("Diarization complete, transcript:", transcriptData);
  };

  const handleDiarizationError = (errorMessage) => {
    setError(errorMessage);
    setIsLoading(false);
    setTranscript(null);
    setProcessedFileName('');
    if (errorMessage) {
      console.error("Diarization error:", errorMessage);
    } else {
      console.log("Diarization error state cleared.");
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
    <div className={styles.diarizationPageContainer}>
      {/* Header specific to this page, or it can be part of App.jsx layout */}
      <header className={styles.pageHeader}>
        <h2>Diarization Tool</h2>
        <p>Upload your .wav file to get started.</p>
      </header>

      <FileUpload
        onUploadSuccess={handleDiarizationComplete}
        onUploadError={handleDiarizationError}
        onProcessingStart={handleProcessingStart}
      />

      {isLoading && (
        <div className={styles.loadingContainer}>
          <div className={styles.hourglass}>⏳</div>
          <p>Processing audio... This may take a few moments.</p>
          <p className={styles.elapsedTime}>
            Time Elapsed: {formatElapsedTime(elapsedTime)}
          </p>
        </div>
      )}

      {error && !isLoading && (
        <div className={styles.errorContainer}>
          <p className={styles.errorMessage}>Error: {error}</p>
        </div>
      )}

      {transcript && !isLoading && !error && (
        <TranscriptEditor
          key={processedFileName} 
          initialTranscript={transcript}
          onTranscriptChange={handleTranscriptSegmentsChange}
          fileName={processedFileName}
        />
      )}
    </div>
  );
}

export default DiarizationPage;

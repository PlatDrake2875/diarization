// frontend/src/components/DiarizationPage/DiarizationPage.jsx
import React, { useState, useEffect, useRef } from 'react';
import FileUpload from '../FileUpload/FileUpload'; 
import TranscriptEditor from '../TranscriptEditor/TranscriptEditor'; 
import styles from './DiarizationPage.module.css';

function DiarizationPage() {
  const [transcript, setTranscript] = useState(null);
  const [isLoading, setIsLoading] = useState(false);
  const [error, setError] = useState('');
  const [processedFileName, setProcessedFileName] = useState('');
  
  const operationStartTimeRef = useRef(null); // Using a ref for start time
  const [elapsedTime, setElapsedTime] = useState(0); 
  const [finalProcessingDuration, setFinalProcessingDuration] = useState(null);
  const timerIntervalRef = useRef(null);

  useEffect(() => {
    if (isLoading && operationStartTimeRef.current) {
      timerIntervalRef.current = setInterval(() => {
        setElapsedTime(Math.floor((Date.now() - operationStartTimeRef.current) / 1000));
      }, 1000);
    } else {
      clearInterval(timerIntervalRef.current);
    }
    return () => clearInterval(timerIntervalRef.current);
  }, [isLoading]); // Removed operationStartTimeRef from dependencies as ref changes don't trigger re-render

  const handleProcessingStart = () => {
    operationStartTimeRef.current = Date.now(); // Set ref at the start
    setIsLoading(true);
    setElapsedTime(0); 
    setFinalProcessingDuration(null); 
    setError('');
    setTranscript(null);
    setProcessedFileName('');
  };

  const handleDiarizationComplete = (transcriptData, originalFileName) => {
    // Calculate duration using the ref's value which was set at the start of the operation
    const duration = operationStartTimeRef.current ? Math.floor((Date.now() - operationStartTimeRef.current) / 1000) : 0;
    setFinalProcessingDuration(duration);
    setTranscript(transcriptData);
    setProcessedFileName(originalFileName);
    setIsLoading(false);
    setError('');
    console.log("Diarization complete, transcript:", transcriptData);
    operationStartTimeRef.current = null; // Reset ref
  };

  const handleDiarizationError = (errorMessage) => {
    const duration = operationStartTimeRef.current ? Math.floor((Date.now() - operationStartTimeRef.current) / 1000) : 0;
    setFinalProcessingDuration(duration);
    setError(errorMessage);
    setIsLoading(false);
    setTranscript(null);
    setProcessedFileName('');
    if (errorMessage) {
      console.error("Diarization error:", errorMessage);
    } else {
      console.log("Diarization error state cleared.");
    }
    operationStartTimeRef.current = null; // Reset ref
  };

  const handleTranscriptSegmentsChange = (updatedSegments) => {
    setTranscript(updatedSegments);
  };

  const formatElapsedTime = (seconds) => {
    if (seconds === null || seconds === undefined) return '00:00';
    const mins = Math.floor(seconds / 60);
    const secs = seconds % 60;
    return `${String(mins).padStart(2, '0')}:${String(secs).padStart(2, '0')}`;
  };

  return (
    <div className={styles.diarizationPageContainer}>
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

      {!isLoading && finalProcessingDuration !== null && (
        <div className={styles.summaryContainer}>
          <p>Total Processing Time: {formatElapsedTime(finalProcessingDuration)}</p>
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

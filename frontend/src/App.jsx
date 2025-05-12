// frontend/src/App.jsx
import React, { useState, useEffect, useRef } from 'react';
import FileUpload from './components/FileUpload/FileUpload';
import TranscriptEditor from './components/TranscriptEditor/TranscriptEditor';
import styles from './App.module.css';

function App() {
  const [transcript, setTranscript] = useState(null);
  const [isLoading, setIsLoading] = useState(false);
  const [error, setError] = useState('');
  const [processedFileName, setProcessedFileName] = useState('');
  
  const [startTime, setStartTime] = useState(null);
  const [elapsedTime, setElapsedTime] = useState(0);
  const timerIntervalRef = useRef(null);

  // Dark Mode State
  const [theme, setTheme] = useState(() => {
    // Get theme from local storage or default to 'light'
    const savedTheme = localStorage.getItem('theme');
    return savedTheme || 'light';
  });

  // Effect to apply theme class to body and save to local storage
  useEffect(() => {
    document.body.className = ''; // Clear previous theme classes
    document.body.classList.add(theme); // Add current theme class (e.g., 'light' or 'dark')
    localStorage.setItem('theme', theme);
  }, [theme]);

  const toggleTheme = () => {
    setTheme(prevTheme => (prevTheme === 'light' ? 'dark' : 'light'));
  };

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
    // The main app container can also have a theme-specific class if needed,
    // but applying to document.body is often more comprehensive.
    <div className={`${styles.appContainer}`}>
      <header className={styles.header}>
        <div className={styles.headerContent}>
          <h1>Audio Diarization & Editor</h1>
          <p>Upload a .wav file, view the diarized transcript, and edit the results.</p>
        </div>
        <button onClick={toggleTheme} className={styles.themeToggleButton}>
          Switch to {theme === 'light' ? 'Dark' : 'Light'} Mode
        </button>
      </header>

      <main className={styles.mainContent}>
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
      </main>

      <footer className={styles.footer}>
        <p>Speaker Diarization Tool - 2024</p>
      </footer>
    </div>
  );
}

export default App;

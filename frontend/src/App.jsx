// frontend/src/App.jsx
import React, { useState, useEffect } from 'react';
import HomePage from './components/HomePage/HomePage';
import DiarizationPage from './components/DiarizationPage/DiarizationPage';
import YouTubeDiarizationPage from './components/YouTubeDiarizationPage/YouTubeDiarizationPage'; // New import
import styles from './App.module.css';

function App() {
  const [currentPage, setCurrentPage] = useState('home'); // 'home', 'diarization', 'youtubeDiarization'
  const [theme, setTheme] = useState(() => {
    const savedTheme = localStorage.getItem('theme');
    return savedTheme || 'light';
  });

  useEffect(() => {
    document.body.className = '';
    document.body.classList.add(theme);
    localStorage.setItem('theme', theme);
  }, [theme]);

  const toggleTheme = () => {
    setTheme(prevTheme => (prevTheme === 'light' ? 'dark' : 'light'));
  };

  const navigateToHome = () => setCurrentPage('home');
  const navigateToDiarization = () => setCurrentPage('diarization');
  const navigateToYouTubeDiarization = () => setCurrentPage('youtubeDiarization'); // New navigation

  return (
    <div className={`${styles.appContainer}`}>
      <header className={styles.header}>
        <div className={styles.headerContent}>
          <h1 onClick={navigateToHome} style={{ cursor: 'pointer' }} className={styles.mainTitle}>
            Speaker Diarization Suite
          </h1>
          {currentPage === 'home' && <p>Welcome! Choose a diarization method.</p>}
          {currentPage === 'diarization' && <p>Process local .wav files.</p>}
          {currentPage === 'youtubeDiarization' && <p>Process audio from YouTube videos.</p>}
        </div>
        <button onClick={toggleTheme} className={styles.themeToggleButton}>
          Switch to {theme === 'light' ? 'Dark' : 'Light'} Mode
        </button>
      </header>

      <main className={styles.mainContent}>
        {currentPage === 'home' && (
          <HomePage 
            navigateToDiarization={navigateToDiarization} 
            navigateToYouTubeDiarization={navigateToYouTubeDiarization} // Pass new nav function
          />
        )}
        {currentPage === 'diarization' && <DiarizationPage />}
        {currentPage === 'youtubeDiarization' && <YouTubeDiarizationPage />} 
      </main>

      <footer className={styles.footer}>
        <p>Speaker Diarization Tool - 2024</p>
      </footer>
    </div>
  );
}

export default App;

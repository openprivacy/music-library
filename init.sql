--	Generate an initial music player database.

DROP DATABASE IF EXISTS music;
CREATE DATABASE music;
USE music;

CREATE TABLE songs (
    id INT AUTO_INCREMENT PRIMARY KEY,
    filepath VARCHAR(1024) NOT NULL,
    artist VARCHAR(255) DEFAULT 'Unknown Artist',
    title VARCHAR(255) DEFAULT 'Unknown Title',
    album VARCHAR(255) DEFAULT 'Unknown Album',
    year VARCHAR(10) DEFAULT NULL,
    genre VARCHAR(100) DEFAULT NULL,
    added_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

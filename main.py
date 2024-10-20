import sys
import re
import cv2
import ytm
import imageio.v3 as iio
from pygame import mixer
from math import floor
from moviepy.editor import VideoFileClip
from PyQt6.QtWidgets import QWidget, QLabel, QApplication, QLineEdit, QTextEdit, QVBoxLayout, QHBoxLayout, QPushButton, QCheckBox
from PyQt6.QtCore import QTimer
from PyQt6.QtGui import QPixmap, QImage
from ytdl import download_video_and_audio
import syncedlyrics
import signal
from play_audio import AudioStreamer
import shutil
import os
import traceback
import json

model = 'hdemucs_mmi'

class MainWindow(QWidget):
    def __init__(self):
        super().__init__()

        self.setWindowTitle("TIDALKaraoke")
        # For more size normalization later
        self.screenWidth = 1080
        self.screenHeight = int((self.screenWidth / 16) * 9)
        self.setGeometry(0, 0, self.screenWidth, self.screenHeight)

        screenLayout = QHBoxLayout()

        leftScreenLayout = QVBoxLayout()

        ### Create searchBar and searchButton
        searchLayout = QHBoxLayout()

        self.searchBar = QLineEdit(self)
        self.searchBar.setPlaceholderText("Enter YouTube link...")
        self.searchBar.setFixedHeight(50)
        self.searchBar.setFixedWidth(500)
        self.searchBar.setStyleSheet("""
            QLineEdit {
                border: 4px solid gray;
                border-radius: 10px;
                padding: 0 8px;
                background: white;
                selection-background-color: darkgray;
                color: black;
            }
        """)
        searchLayout.addWidget(self.searchBar)

        self.searchButton = QPushButton(self)
        self.searchButton.setText("Search")
        self.searchButton.setFixedWidth(75)
        self.searchButton.setFixedHeight(50)
        self.searchButton.clicked.connect(self.onSearchButtonClick)

        searchLayout.addWidget(self.searchButton)

        checkboxLayout = QHBoxLayout()

        self.checkbox1 = QCheckBox("vocals", self)
        self.checkbox2 = QCheckBox("bass", self)
        self.checkbox3 = QCheckBox("drums", self)
        self.checkbox4 = QCheckBox("other", self)

        self.checkbox1.setChecked(True)
        self.checkbox2.setChecked(True)
        self.checkbox3.setChecked(True)
        self.checkbox4.setChecked(True)

        checkboxLayout.addWidget(self.checkbox1)
        checkboxLayout.addWidget(self.checkbox2)
        checkboxLayout.addWidget(self.checkbox3)
        checkboxLayout.addWidget(self.checkbox4)

        # on checkbox change
        self.checkbox1.stateChanged.connect(self.onCheckboxChange)
        self.checkbox2.stateChanged.connect(self.onCheckboxChange)
        self.checkbox3.stateChanged.connect(self.onCheckboxChange)
        self.checkbox4.stateChanged.connect(self.onCheckboxChange)
        
        ### Create videoLabel that holds pixelMap, connect it to timed update function
        self.videoLabel = QLabel(self)
        self.videoLabel.setStyleSheet("""
            QLabel {
                border: 4px solid gray;
                border-radius: 10px;
            }
        """)

        self.isRenderingVideo = False
        self.video = None
        self.videoFPS = None
        self.videoTimer = None  # Initialize video timer to None
        
        self.videoLabel.setPixmap(QPixmap(600, 540))
        
        # Create layout that holds control buttons
        videoControlLayout = QHBoxLayout()
        
        self.audio_streamer = None

        self.playButton = QPushButton(self)
        self.playButton.setText("Play")
        self.playButton.setFixedWidth(75)
        self.playButton.setFixedHeight(50)
        self.playButton.clicked.connect(self.onPlayButtonClicked)

        self.pauseButton = QPushButton(self)
        self.pauseButton.setText("Pause")
        self.pauseButton.setFixedWidth(75)
        self.pauseButton.setFixedHeight(50)
        self.pauseButton.clicked.connect(self.onPauseButtonClicked)

        
        videoControlLayout.addWidget(self.playButton)
        videoControlLayout.addWidget(self.pauseButton)

        ### Create lyricsLabel that holds lyrics
        lyricBoxLayout = QVBoxLayout()

        self.lyricBox = QTextEdit(self)
        self.lyricBox.setFixedWidth(400)
        self.lyricBox.setFixedHeight(600)
        self.lyricBox.setReadOnly(True)
        self.isRenderingLyrics = False
        self.lyrics = None
        self.lyricIndex = None

        self.lyricBox.setStyleSheet("""
            QTextEdit {
                border: 4px solid gray;
                border-radius: 10px;
                padding: 0 8px;
                background: black;
                selection-background-color: darkgray;
                color: white;
                font-size: 40px;
            }
        """)
        lyricBoxLayout.addWidget(self.lyricBox)
        
        # Setup lyrics timer
        self.lyricsTimer = QTimer(self)
        self.lyricsTimer.setInterval(100)  # Update lyrics every 100 ms
        self.lyricsTimer.timeout.connect(self.renderLyrics)
        
        ### Show screen
        leftScreenLayout.addLayout(searchLayout)
        leftScreenLayout.addLayout(checkboxLayout)
        leftScreenLayout.addWidget(self.videoLabel)
        leftScreenLayout.addLayout(videoControlLayout)

        screenLayout.addLayout(leftScreenLayout)
        screenLayout.addLayout(lyricBoxLayout)

        self.setLayout(screenLayout)

        self.ytm_api = ytm.YouTubeMusic()
        # clear temp folder
        shutil.rmtree('temp', ignore_errors=True)
        os.makedirs('temp', exist_ok=True)

    def onCheckboxChange(self):
        options = []
        if self.checkbox1.isChecked():
            options.append('vocals')
        if self.checkbox2.isChecked():
            options.append('bass')
        if self.checkbox3.isChecked():
            options.append('drums')
        if self.checkbox4.isChecked():
            options.append('other')
        print(options)

        self.audio_streamer.change_tracks(options)

    def onSearchButtonClick(self):
        if self.audio_streamer:
            self.audio_streamer.stop()
            self.audio_streamer = None

        youTubeLinkRegex = re.compile(r'^(https?://)?(www\.)?(youtube\.com|youtu\.be)/(watch\?v=|embed/|v/)?([A-Za-z0-9_-]{11})(&.*)*$') #Test Later

        if (youTubeLinkRegex.fullmatch(self.searchBar.text())):

            video_url, audio_path, info_dict = download_video_and_audio(self.searchBar.text(), output_dir='temp')

            ### Audio setup
            self.audio_streamer = AudioStreamer(audio_path, f'temp/{model}')
            signal.signal(signal.SIGINT, self.audio_streamer.handle_signal)  # Handle CTRL+C
            self.audio_streamer.start()

            ### Video setup
            self.isRenderingVideo = True
            self.video = cv2.VideoCapture(video_url)
            self.videoFPS = self.video.get(cv2.CAP_PROP_FPS)

            # Setup video timer
            self.videoTimer = QTimer(self)
            self.videoTimer.setInterval(int(1000 / self.videoFPS))
            self.videoTimer.timeout.connect(self.updateVideoFrame)
            self.videoTimer.start()
        
            ### Lyric setup

            res = self.ytm_api.search_songs(info_dict['title'])['items'][0]
            song_name = res['name']
            artist_name = res['artists'][0]['name']
            lyrics = syncedlyrics.search(f"[{song_name}] [{artist_name}]", synced_only=True)
            print(f"[{song_name}] [{artist_name}]")
            if not lyrics:
                lyrics = 'No lyrics found'
            
            self.isRenderingLyrics = True
            tempLyrics = lyrics.splitlines()
            for i in range(len(tempLyrics)):
                minutes, seconds = tempLyrics[i][1:9].split(":")
                minutes, seconds = int(minutes), float(seconds)
                milliseconds = int(floor((minutes * 60 + seconds) * 1000))
                tempLyrics[i] = (milliseconds, tempLyrics[i][tempLyrics[i].index(']')+1:].strip())
            self.lyrics = tempLyrics
            self.lyricIndex = 0
            self.updateLyrics()
            self.lyricsTimer.start()  # Start lyrics timer
    
    def onPlayButtonClicked(self):
        self.audio_streamer.play()
        self.isRenderingVideo = True
        if self.videoTimer is not None:
            self.videoTimer.start()
        if self.lyricsTimer is not None:
            self.lyricsTimer.start()

    def onPauseButtonClicked(self):
        self.audio_streamer.pause()
        self.isRenderingVideo = False
        if self.videoTimer is not None:
            self.videoTimer.stop()
        if self.lyricsTimer is not None:
            self.lyricsTimer.stop()

    def updateVideoFrame(self):
        try:
            if self.isRenderingVideo:
                # frameNumber = self.audio_streamer.get_pos() * self.videoFPS / 1000
                # self.video.set(cv2.CAP_PROP_POS_FRAMES, frameNumber)
                while self.audio_streamer.get_pos() == 0:
                    pass

                ret, frame = self.video.read()
                if not ret:
                    print("Failed to retrieve frame")
                    self.videoTimer.stop()
                    return
                
                h, w, ch = frame.shape
                bytesPerLine = ch * w
                frameImage = QImage(frame.data, w, h, bytesPerLine, QImage.Format.Format_RGB888)
                frameImagePixmap = QPixmap.fromImage(frameImage)
                self.videoLabel.setPixmap(frameImagePixmap)
                
        except Exception as e:
            print(f"Error rendering video: {e}")
            print(traceback.format_exc())

    def renderLyrics(self):
        if self.isRenderingLyrics:
            if self.lyricIndex < len(self.lyrics) - 1:
                if self.audio_streamer.get_pos() >= self.lyrics[self.lyricIndex+1][0]:
                    self.lyricIndex = self.lyricIndex + 1
                    self.updateLyrics()
        
    def updateLyrics(self):
        if self.lyricIndex == len(self.lyrics) - 1:
            self.lyricBox.setHtml("<b>" + self.lyrics[self.lyricIndex][1] + "</b>" + "<br>" + "<br>")
        elif self.lyricIndex == len(self.lyrics) - 2:
            self.lyricBox.setText("<b>" + self.lyrics[self.lyricIndex][1] + "</b>" + "<br>" + "<br>" +
                                  self.lyrics[self.lyricIndex+1][1] + "<br>" + "<br>")
        else: 
            self.lyricBox.setText("<b>" + self.lyrics[self.lyricIndex][1] + "</b>" + "<br>" + "<br>" +
                                  self.lyrics[self.lyricIndex+1][1] + "<br>" + "<br>" +
                                  self.lyrics[self.lyricIndex+2][1] + "<br>" + "<br>")


def handleClose():
    if window.audio_streamer:
        window.audio_streamer.stop()
    if window.videoTimer:
        window.videoTimer.stop()
    if window.lyricsTimer:
        window.lyricsTimer.stop()
    app.quit()

app = QApplication(sys.argv)
mixer.init()
window = MainWindow()
window.show()
app.aboutToQuit.connect(handleClose)
app.exec()

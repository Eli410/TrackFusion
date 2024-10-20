import sys
import re
import cv2
import threading
import imageio.v3 as iio
from pygame import mixer
from math import floor
from moviepy.editor import VideoFileClip
from PyQt6.QtWidgets import QWidget, QLabel, QApplication, QLineEdit, QTextEdit, QVBoxLayout, QHBoxLayout, QPushButton
from PyQt6.QtCore import QTimer
from PyQt6.QtGui import QPixmap, QKeyEvent, QImage
from ytdl import download_video_and_audio
import syncedlyrics
from processing import process_audio_sync
import signal
from play_audio import AudioStreamer
import shutil
import os


model = 'hdemucs_mmi'
class MainWindow(QWidget):
    def __init__(self):
        super().__init__()

        self.setWindowTitle("TIDALKaraoke")
        self.setGeometry(0, 0, 1080, 720)
        screenLayout = QHBoxLayout()

        leftScreenLayout = QVBoxLayout()

        ### Create searchBar and searchButton
        ###
        ###
        ###
        searchLayout = QHBoxLayout()

        self.searchBar = QLineEdit(self)
        self.searchBar.setPlaceholderText("Enter YouTube link...")
        self.searchBar.setFixedHeight(50)
        self.searchBar.setFixedWidth(500)
        self.searchBar.setStyleSheet("""
            QLineEdit {
                border: 2px solid gray;
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

        ### Create videoLabel that holds pixelMap, connect it to timed update function
        ###
        ###
        ###
        self.videoLabel = QLabel(self)
        self.isRenderingVideo = False
        self.video = None
        self.videoFPS = None
        
        self.videoLabel.setPixmap(QPixmap(600, 540))
        self.timer = QTimer(self)
        
        self.renderVideoThread = threading.Thread(target=self.renderVideo)
        self.renderVideoThread.start()
        self.timer.timeout.connect(self.startRenderVideoThread)

        #Create layout that holds control buttons
        ###
        ###
        ###
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
        ###
        ###
        ###
        lyricBoxLayout = QVBoxLayout()

        self.lyricBox = QTextEdit(self)
        self.lyricBox.setFixedWidth(300)
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
        
        # self.renderVideoThread = threading.Thread(target=self.renderLyrics)
        # self.renderVideoThread.start()
        # self.timer.timeout.connect(self.startRenderLyricsThread)
        self.timer.timeout.connect(self.renderLyrics)
        self.timer.start(1)
        
        ### Show screen
        ###
        ###
        ###
        leftScreenLayout.addLayout(searchLayout)
        leftScreenLayout.addWidget(self.videoLabel)
        leftScreenLayout.addLayout(videoControlLayout)

        screenLayout.addLayout(leftScreenLayout)
        screenLayout.addLayout(lyricBoxLayout)

        self.setLayout(screenLayout)

        # clear temp folder
        shutil.rmtree('temp', ignore_errors=True)
        os.makedirs('temp', exist_ok=True)

    def startRenderVideoThread(self):
        if not self.renderVideoThread.is_alive():
            self.renderVideoThread = threading.Thread(target=self.renderVideo)
            self.renderVideoThread.start()

    def onSearchButtonClick(self):
        # mixer.music.stop()
        # mixer.music.unload()

        # self.searchBar.setText("https://www.youtube.com/watch?v=B9synWjqBn8")
        youTubeLinkRegex = re.compile(r'^(https?://)?(www\.)?(youtube\.com|youtu\.be)/(watch\?v=|embed/|v/)?([A-Za-z0-9_-]{11})(&.*)*$') #Test Later
        self.searchButton.setEnabled(False)

        if (youTubeLinkRegex.fullmatch(self.searchBar.text())):

            video_path, audio_path, info_dict = download_video_and_audio(self.searchBar.text(), output_dir='temp')

            ### Audio setup
            # mixer.music.load(f"temp/{info_dict['title']}.mp3")
            # mixer.music.play()

            self.audio_streamer = AudioStreamer(audio_path, f'temp/{model}')
            signal.signal(signal.SIGINT, self.audio_streamer.handle_signal)  # Handle CTRL+C
            self.audio_streamer.start()

            ### Video setup
            self.isRenderingVideo = True
            self.videoFPS = iio.immeta(video_path, exclude_applied=False).get('fps', None)
            self.video = cv2.VideoCapture(video_path)

            ### Lyric setup
            lyrics = syncedlyrics.search(f"[{info_dict['title']}]", synced_only=True) 
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

    def onPlayButtonClicked(self):
        # mixer.music.unpause()
        self.audio_streamer.play()
        self.isRenderingVideo = True

    def onPauseButtonClicked(self):
        # mixer.music.pause()
        self.audio_streamer.pause()
        self.isRenderingVideo = False

    def renderVideo(self):
        if self.isRenderingVideo:
            title = "B9synWjqBn8"
            frameNumber = (floor((self.audio_streamer.get_pos() / 1000) * self.videoFPS))-1
            self.video.set(cv2.CAP_PROP_POS_FRAMES, frameNumber)
            ret, frame = self.video.read()
            frame = cv2.resize(frame, (854, 480))
            frame = cv2.cvtColor(frame, cv2.COLOR_RGB2BGR)
            h, w, ch = frame.shape
            bytesPerLine = ch * w
            frameImage = QImage(frame.data, w, h, bytesPerLine, QImage.Format.Format_RGB888)
            frameImagePixmap = QPixmap.fromImage(frameImage)
            self.videoLabel.setPixmap(frameImagePixmap)
    
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


app = QApplication(sys.argv)
mixer.init()
window = MainWindow()
window.show()
app.exec()
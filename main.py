import sys
import re
import cv2
import threading
import imageio.v3 as iio
from pygame import mixer
from math import floor
from moviepy.editor import VideoFileClip
from PyQt6.QtWidgets import QWidget, QLabel, QApplication, QLineEdit, QVBoxLayout, QHBoxLayout, QPushButton
from PyQt6.QtCore import QTimer
from PyQt6.QtGui import QPixmap, QKeyEvent, QImage

class MainWindow(QWidget):
    def __init__(self):
        super().__init__()

        self.setWindowTitle("TIDALKaraoke")
        self.setGeometry(0, 0, 1080, 720)

        screenLayout = QHBoxLayout()

        leftScreenLayout = QVBoxLayout()

        #Create searchBar and searchButton
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

        #Create videoLabel that holds pixelMap, connect it to timed update function
        self.videoLabel = QLabel(self)
        self.isRenderingVideo = False
        self.video = None
        self.videoFPS = None
        
        self.videoLabel.setPixmap(QPixmap(600, 540))
        self.timer = QTimer(self)
        
        self.renderVideoThread = threading.Thread(target=self.renderVideo)
        self.renderVideoThread.start()
        self.timer.timeout.connect(self.start_render_video_thread)
        self.timer.start(1)  # 1000 ms = 1 s, 30 fps

        #Create layout that holds control buttons
        ###
        videoControlLayout = QHBoxLayout()

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


        #Create lyricsLabel that holds lyrics
        lyricBoxLayout = QVBoxLayout()

        self.lyricBox = QLineEdit(self)
        self.lyricBox.setFixedWidth(300)
        self.lyricBox.setFixedHeight(600)
        self.lyricBox.setReadOnly(True)

        self.lyricBox.setStyleSheet("""
            QLineEdit {
                border: 2px solid gray;
                border-radius: 10px;
                padding: 0 8px;
                background: white;
                selection-background-color: darkgray;
                color: black;
            }
        """)
        lyricBoxLayout.addWidget(self.lyricBox)
        
        #Show screen
        leftScreenLayout.addLayout(searchLayout)
        leftScreenLayout.addWidget(self.videoLabel)
        leftScreenLayout.addLayout(videoControlLayout)

        screenLayout.addLayout(leftScreenLayout)
        screenLayout.addLayout(lyricBoxLayout)

        self.setLayout(screenLayout)

    def start_render_video_thread(self):
        if not self.renderVideoThread.is_alive():
            self.renderVideoThread = threading.Thread(target=self.renderVideo)
            self.renderVideoThread.start()

    def onSearchButtonClick(self):
        mixer.music.stop()
        mixer.music.unload()

        self.searchBar.setText("https://www.youtube.com/watch?v=B9synWjqBn8")
        # print(self.searchBar.text())
        youTubeLinkRegex = re.compile(r'^(https?://)?(www\.)?(youtube\.com|youtu\.be)/(watch\?v=|embed/|v/)?([A-Za-z0-9_-]{11})(&.*)*$') #Test Later
        if (youTubeLinkRegex.fullmatch(self.searchBar.text())):
            title = "B9synWjqBn8"
            mixer.music.load(f"tests/{title}.mp3")
            mixer.music.play()
            self.isRenderingVideo = True
            self.videoFPS = iio.immeta(f"tests/{title}.mp4", exclude_applied=False).get('fps', None)
            self.video = cv2.VideoCapture(f"tests/{title}.mp4")
            print(self.videoFPS)

    def onPlayButtonClicked(self):
        mixer.music.unpause()
        self.isRenderingVideo = True

    def onPauseButtonClicked(self):
        mixer.music.pause()
        self.isRenderingVideo = False

    def renderVideo(self):
        if self.isRenderingVideo:
            title = "B9synWjqBn8"
            frameNumber = (floor((mixer.music.get_pos() / 1000) * self.videoFPS))-1
            self.video.set(cv2.CAP_PROP_POS_FRAMES, frameNumber)
            ret, frame = self.video.read()
            frame = cv2.resize(frame, (600, 540))
            frame = cv2.cvtColor(frame, cv2.COLOR_RGB2BGR)
            h, w, ch = frame.shape
            bytesPerLine = ch * w
            frameImage = QImage(frame.data, w, h, bytesPerLine, QImage.Format.Format_RGB888)
            frameImagePixmap = QPixmap.fromImage(frameImage)
            self.videoLabel.setPixmap(frameImagePixmap)



app = QApplication(sys.argv)
mixer.init()
window = MainWindow()
window.show()
app.exec()
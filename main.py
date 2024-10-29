import sys
import re
import cv2
import ytm
import imageio.v3 as iio
from math import floor
from PyQt6.QtWidgets import (QWidget, QLabel, QApplication, QLineEdit, QVBoxLayout, 
                             QHBoxLayout, QPushButton, QCheckBox, QStyledItemDelegate, QCompleter,
                             QMessageBox,)
from PyQt6.QtCore import QTimer, QSize, Qt, QRect, QStringListModel, pyqtSignal, QThread
from PyQt6.QtGui import QPixmap, QImage, QColor, QFont, QPainter, QPen
import syncedlyrics
import signal
from streamer import AudioStreamer

from qtComponents import AutocompleteDelegate, AutocompleteModel, ytdl_Worker

model = 'hdemucs_mmi'

class MainWindow(QWidget):
    def __init__(self):
        super().__init__()
        self.audio_streamer = AudioStreamer()
        self.setWindowTitle("TrackFusion")
        # For more size normalization later
        self.screenWidth = 1080
        self.screenHeight = int((self.screenWidth / 16) * 9)
        self.setGeometry(0, 0, self.screenWidth, self.screenHeight)

        screenLayout = QHBoxLayout()

        leftScreenLayout = QVBoxLayout()

        ### Create searchBar and searchButton
        searchLayout = QHBoxLayout()

        self.searchBar = QLineEdit(self)
        self.searchBar.setPlaceholderText("Search or enter YouTube link...")
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
        self.searchBar.returnPressed.connect(self.onSearchButtonClick)
        
        searchLayout.addStretch(1)  # Add stretchable space before the search bar
        searchLayout.addWidget(self.searchBar)

        self.searchButton = QPushButton(self)
        self.searchButton.setText("Play")
        self.searchButton.setFixedWidth(75)
        self.searchButton.setFixedHeight(50)
        self.searchButton.clicked.connect(self.onSearchButtonClick)

        self.debugDisplay = QLabel(self)
        self.debugDisplay.setFixedWidth(200)
        self.debugDisplay.setFixedHeight(50)

        self.debugTimer = QTimer(self)
        self.debugTimer.setInterval(10)
        self.debugTimer.timeout.connect(self.setDebugText)
        self.debugTimer.start()

        searchLayout.addWidget(self.searchButton)
        searchLayout.addStretch(1)  # Add stretchable space after the search button
        searchLayout.addWidget(self.debugDisplay)

        self.timer = QTimer(self)
        self.timer.setInterval(800)
        self.timer.setSingleShot(True)
        self.timer.timeout.connect(self.show_completer)

        self.thumbnail = None
        self.isRenderingLyrics = False
        
        # Connect textChanged signal to restart timer
        self.searchBar.textChanged.connect(self.on_text_changed)


        # Initialize Completer
        self.completer = QCompleter(self)
        self.model = AutocompleteModel(self)
        self.completer.setModel(self.model)
        self.completer.setWidget(self.searchBar)
        self.completer.setCompletionMode(QCompleter.CompletionMode.PopupCompletion)
        self.completer.setCaseSensitivity(Qt.CaseSensitivity.CaseInsensitive)
        self.completer.activated.connect(self.on_suggestion_selected)

        # Set custom delegate
        delegate = AutocompleteDelegate(self.completer.popup())
        self.completer.popup().setItemDelegate(delegate)

        # Optional: Adjust completer popup size
        self.completer.popup().setMinimumWidth(500)
        self.completer.popup().setMinimumHeight(200)
        checkboxLayout = QHBoxLayout()

        self.track_checkboxes = []
        for track in self.audio_streamer.selected_tracks[::-1]:

            checkbox = QCheckBox(track, self)
            checkbox.setChecked(True)
            checkboxLayout.addStretch(1)
            checkboxLayout.addWidget(checkbox)
            checkbox.stateChanged.connect(self.onCheckboxChange)
            self.track_checkboxes.append(checkbox)

        checkboxLayout.addStretch(1)
        
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
                        
        # Create layout that holds control buttons
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
        # screenLayout.addLayout(lyricBoxLayout)

        self.setLayout(screenLayout)

        self.ytm_api = ytm.YouTubeMusic()
    
        self.thread = None

    def setDebugText(self):
        curr_time = self.audio_streamer.get_pos()
        self.debugDisplay.setText(f"{curr_time / 1000:.2f} Seconds")


    def onCheckboxChange(self):
        options = [checkbox.text() for checkbox in self.track_checkboxes if checkbox.isChecked()]
        if self.audio_streamer:
            self.audio_streamer.change_tracks(options)

    def get_thumbnail(self, url):
        image = iio.imread(url)
        height, width, _ = image.shape
        aspect_ratio = width / height
        new_width = self.videoLabel.width()
        new_height = int(new_width / aspect_ratio)
        image = cv2.resize(image, (new_width, new_height))
        qimage = QImage(image.data, image.shape[1], image.shape[0], QImage.Format.Format_RGB888)
        frameImagePixmap = QPixmap.fromImage(qimage)
        return frameImagePixmap

    def setup_playback(self, audio_url, thumbnail_url, info_dict, loadingMsg):
        loadingMsg.accept()
        # Set pixmap to the thumbnail_url
        self.thumbnail = self.get_thumbnail(thumbnail_url)
        self.videoLabel.setPixmap(self.thumbnail)

        ### Audio setup
        self.audio_streamer.set_youtube_url(audio_url)
        signal.signal(signal.SIGINT, self.audio_streamer.handle_signal)  # Handle CTRL+C
        self.audio_streamer.start_stream()
        
        ### Lyric setup
        lyrics = None
        res = self.ytm_api.search_songs(info_dict['title'])['items'][0]
        song_name = res['name'] or 'Unknown'
        artist_name = res['artists'][0]['name'] or 'Unknown'
        if song_name != 'Unknown' and artist_name != 'Unknown':
            lyrics = syncedlyrics.search(f"[{song_name}] [{artist_name}]", synced_only=True)
        elif song_name != 'Unknown':
            lyrics = syncedlyrics.search(f"[{song_name}]", synced_only=True)
        
        if not lyrics:
            lyrics = 'No lyrics found'
            # self.lyricBox.setText(lyrics)
        else:
            self.isRenderingLyrics = True
            tempLyrics = lyrics.splitlines()
            for i in range(len(tempLyrics)):
                minutes, seconds = tempLyrics[i][1:9].split(":")
                minutes, seconds = int(minutes), float(seconds)
                milliseconds = int(floor((minutes * 60 + seconds) * 1000))
                tempLyrics[i] = (milliseconds, tempLyrics[i][tempLyrics[i].index(']')+1:].strip())
            self.lyrics = tempLyrics
            self.lyricIndex = 0
            self.lyricsTimer.start()
            self.updateLyrics()

    def onSearchButtonClick(self):
        if self.audio_streamer:
            self.audio_streamer.cleanup()

        self.onCheckboxChange()

        youTubeLinkRegex = re.compile(r'^(https?://)?(www\.)?(youtube\.com|youtu\.be)/(watch\?v=|embed/|v/)?([A-Za-z0-9_-]{11})(&.*)*$') #Test Later

        if (youTubeLinkRegex.fullmatch(self.searchBar.text())):
            loadingMsg = QMessageBox()
            loadingMsg.setIcon(QMessageBox.Icon.Information)
            loadingMsg.setText("Loading... Please wait.")
            loadingMsg.show()  # Show the loading message
            self.thread = ytdl_Worker(self.searchBar.text(), loadingMsg)
            self.thread.finished.connect(self.setup_playback)  # Connect the finished signal to the onFinished slot
            self.thread.start()
        else:
            # show pyqt error dialog
            error_dialog = QMessageBox(self)
            error_dialog.setIcon(QMessageBox.Icon.Critical)
            error_dialog.setText("Invalid YouTube URL")
            error_dialog.setWindowTitle("Error")
            error_dialog.exec()

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


    def renderLyrics(self):
        if self.isRenderingLyrics:
            if self.lyricIndex < len(self.lyrics) - 1:
                if self.audio_streamer.get_pos() >= self.lyrics[self.lyricIndex+1][0]:
                    self.lyricIndex = self.lyricIndex + 1
                    self.updateLyrics()

    def adjustLyrics(self):
        if self.isRenderingLyrics:
            if self.sender().text() == "+ 0.5":
                for i in range(len(self.lyrics)):
                    self.lyrics[i] = (self.lyrics[i][0] + 500, self.lyrics[i][1])
                self.updateLyrics()


            elif self.sender().text() == "- 0.5":
                for i in range(len(self.lyrics)):
                    self.lyrics[i] = (self.lyrics[i][0] - 500, self.lyrics[i][1])
                self.updateLyrics()


    def updateLyrics(self):
        if self.lyricIndex < len(self.lyrics):
            lyrics_text = self.lyrics[self.lyricIndex][1]
        else:
            lyrics_text = ""
        
        lyrics_text += '\n'

        current_pixmap = self.thumbnail.copy()
        if current_pixmap:
            fontSize = 24
            painter = QPainter(current_pixmap)
            
            # Set font with a bold style and larger size for better visibility
            font = QFont("Arial", fontSize, QFont.Weight.Bold)
            painter.setFont(font)
            
            textColor = QColor("white")
            outlineColor = QColor("black")
            
            # Drawing outline for better visibility on complex backgrounds
            outlineWidth = 5  # Adjust the pen width to the outline thickness
            painter.setPen(QPen(outlineColor, outlineWidth))
            for dx, dy in [(-outlineWidth, 0), (outlineWidth, 0), (0, -outlineWidth), (0, outlineWidth),
                   (-outlineWidth, -outlineWidth), (-outlineWidth, outlineWidth), 
                   (outlineWidth, -outlineWidth), (outlineWidth, outlineWidth)]:
                painter.drawText(current_pixmap.rect().adjusted(dx, dy, dx, dy), Qt.AlignmentFlag.AlignBottom | Qt.AlignmentFlag.AlignHCenter, lyrics_text)
            
            # Drawing the main text
            painter.setPen(QPen(textColor))
            painter.drawText(current_pixmap.rect(), Qt.AlignmentFlag.AlignBottom | Qt.AlignmentFlag.AlignHCenter, lyrics_text)
            
            painter.end()
            self.videoLabel.setPixmap(current_pixmap)
            # Drawing the main text
            painter.setPen(QPen(textColor))
            painter.drawText(current_pixmap.rect(), Qt.AlignmentFlag.AlignBottom | Qt.AlignmentFlag.AlignHCenter, lyrics_text)
            
            painter.end()
            self.videoLabel.setPixmap(current_pixmap)


    def on_text_changed(self, text):
        if text:
            self.timer.start()
        else:
            self.completer.popup().hide()

    def on_suggestion_selected(self, suggestion):
        # This method is called when a suggestion is clicked. The suggestion parameter will be the text of the selected item.
        for text, id in self.model.suggestions:
            if text == suggestion:
                yt_url = f'https://www.youtube.com/watch?v={id}'
                self.searchBar.textChanged.disconnect(self.on_text_changed)
                self.searchBar.setText(yt_url)
                self.searchBar.textChanged.connect(self.on_text_changed)
                break

    def show_completer(self):
        text = self.searchBar.text()
        if text:
            try:
                # suggestion = self.ytm_api.search_videos(text)['items'][:5]
                suggestion = (self.ytm_api.search_songs(text)['items'][:10])
        
                suggestions = []
                for song in suggestion:
                    song_name = song.get('name')
                    artist_name = song.get('artists', [{}])[0].get('name')
                    display_text = f"{song_name} - {artist_name}" if artist_name else song_name
                    suggestions.append((display_text, song.get('videoId', song.get('id'))))
                self.model.set_data(suggestions)
                self.completer.complete()
            except Exception as e:
                print(f"Error searching for songs: {e}")
                self.ytm_api = ytm.YouTubeMusic()
                suggestion = []
    
    
def handleClose():
    window.audio_streamer.cleanup()
    if window.lyricsTimer:
        window.lyricsTimer.stop()
    app.quit()
    sys.exit()



app = QApplication(sys.argv)
window = MainWindow()
window.show()
app.aboutToQuit.connect(handleClose)
app.exec()

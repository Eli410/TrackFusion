import sys
import re
import cv2
from ytm.apis import YouTubeMusic
from PyQt6.QtWidgets import (QWidget, QLabel, QApplication, QLineEdit, QVBoxLayout, 
                             QHBoxLayout, QPushButton, QCheckBox, QCompleter,
                             QMessageBox, QMenuBar, QToolBar, QMainWindow)
from PyQt6.QtCore import QTimer, Qt, QThread, pyqtSignal, QObject
from PyQt6.QtGui import QPixmap, QImage, QColor, QFont, QPainter, QPen, QIcon, QAction
import syncedlyrics
import signal
from streamer import AudioStreamer

from qtComponents import AutocompleteDelegate, AutocompleteModel, ytdl_Worker, VideoWindow
import requests
import numpy as np
from LRC import LRCParser


class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("TrackFusion")
        self.mainScreen = MainScreen()
        self.setCentralWidget(self.mainScreen)
        self.setGeometry(0, 0, self.mainScreen.screenWidth, self.mainScreen.screenHeight)
        self._createMenuBar()
        self.centerOnScreen()
        self.show()

    def centerOnScreen(self):
        screen = QApplication.primaryScreen().availableGeometry()
        x = (screen.width() - self.width()) // 2
        y = (screen.height() - self.height()) // 2
        self.move(x, y)

    def resizeEvent(self, event):
        self.centerOnScreen()
        super().resizeEvent(event)

    def _createMenuBar(self):
        # clear the existing menu bar
        self.menuBar().clear()

        menuBar = self.menuBar()
        # Create a model menu
        self.modelMenu = menuBar.addMenu('Model')
        self.lyricMenu = menuBar.addMenu('Lyrics')
        
        action = self.lyricMenu.addAction('Word Level')
        action.setCheckable(True)
        action.setChecked(self.mainScreen.word_level_lyrics)
        action.triggered.connect(lambda: setattr(self.mainScreen, 'word_level_lyrics', not self.mainScreen.word_level_lyrics))

        self.lyricMenu.addAction('+ 0.5').triggered.connect(self.mainScreen.adjustLyrics)
        self.lyricMenu.addAction('- 0.5').triggered.connect(self.mainScreen.adjustLyrics)

        
        # Add model options to the menu
        self.modelOptions = [
            'hdemucs_mmi', 
            'htdemucs', 
            'htdemucs_6s', 
            'mdx',
            'mdx_extra',
            'mdx_q',
            'mdx_extra_q'
            ]
        
        for option in self.modelOptions:
            action = self.modelMenu.addAction(option)
            action.setCheckable(True)
            if option == self.mainScreen.audio_streamer.model:
                action.setChecked(True)
            action.triggered.connect(lambda _, option=option: self.mainScreen.change_model(option, self._createMenuBar))

class MainScreen(QWidget):
    def __init__(self):
        super().__init__()
        self.audio_streamer = AudioStreamer()
        self.setWindowTitle("TrackFusion")
        # For more size normalization later
        self.screenWidth = 1080
        self.screenHeight = int((self.screenWidth / 16) * 9)
        self.setGeometry(0, 0, self.screenWidth, self.screenHeight)
        # Center the window on the screen
        screen = QApplication.primaryScreen().availableGeometry()
        x = (screen.width() - self.screenWidth) // 2
        y = (screen.height() - self.screenHeight) // 2
        self.move(x, y)
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
        self.currentScreen = None
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
        self.checkboxLayout = QHBoxLayout()

        self.track_checkboxes = []
        self.update_checkboxes()

        self.checkboxLayout.addStretch(1)
        
        self.videoLabel = VideoWindow(self)
        self.videoLabel.clicked.connect(self.togglePlayPause)


        self.isPaused = False
        self.video = None
        self.videoFPS = None
        self.videoTimer = None  # Initialize video timer to None
                        

        # Setup lyrics timer
        self.lyricsTimer = QTimer(self)
        self.lyricsTimer.setInterval(100)  # Update lyrics every 100 ms
        self.lyricsTimer.timeout.connect(self.renderLyrics)
        
        ### Show screen
        leftScreenLayout.addLayout(searchLayout)
        leftScreenLayout.addLayout(self.checkboxLayout)
        leftScreenLayout.addWidget(self.videoLabel)

        screenLayout.addLayout(leftScreenLayout)

        self.setLayout(screenLayout)

        self.ytm_api = YouTubeMusic()
    
        self.thread = None

        self.word_level_lyrics = False

    def setDebugText(self):
        self.debugDisplay.setText(f"Current model: {self.audio_streamer.model}")

    def update_checkboxes(self):
        # Clear the existing checkboxes and stretch
        while self.checkboxLayout.count():
            item = self.checkboxLayout.takeAt(0)
            widget = item.widget()
            if widget is not None:
                widget.setParent(None)
        
        self.track_checkboxes = []
        for track in self.audio_streamer.selected_tracks[::-1]:
            checkbox = QCheckBox(track, self)
            checkbox.setChecked(True)
            self.checkboxLayout.addStretch(1)
            self.checkboxLayout.addWidget(checkbox)
            checkbox.stateChanged.connect(self.onCheckboxChange)
            self.track_checkboxes.append(checkbox)
        
        self.checkboxLayout.addStretch(1)  # Add a single stretch at the end

    def onCheckboxChange(self):
        options = [checkbox.text() for checkbox in self.track_checkboxes if checkbox.isChecked()]
        if self.audio_streamer:
            self.audio_streamer.change_tracks(options)

    def change_model(self, model, reset_menu):
        if self.audio_streamer.is_playing():
            warning = QMessageBox()
            warning.setIcon(QMessageBox.Icon.Warning)
            warning.setText("Changing the model will restart the current playback. Do you want to continue?")
            warning.setWindowTitle("Warning")
            warning.setStandardButtons(QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No)
            warning.setDefaultButton(QMessageBox.StandardButton.No)
            response = warning.exec()
            if response == QMessageBox.StandardButton.Yes:            
                self.audio_streamer.set_model(model)
                print(self.audio_streamer.selected_tracks)
                self.update_checkboxes()
                self.audio_streamer.restart()

            reset_menu()

        else:
            self.audio_streamer.set_model(model)
            print(self.audio_streamer.selected_tracks)
            self.update_checkboxes()
            reset_menu()
        

    def get_thumbnail(self, url):
        # Download the image from the URL
        response = requests.get(url)
        image_array = np.array(bytearray(response.content), dtype=np.uint8)
        image = cv2.imdecode(image_array, cv2.IMREAD_COLOR)
        
        # Check if the image was loaded (not empty)
        if image is None:
            print("Failed to load image")
            return None

        # Convert from BGR to RGB
        image = cv2.cvtColor(image, cv2.COLOR_BGR2RGB)
        
        # Calculate the new dimensions
        height, width, channels = image.shape
        if channels == 3:  # Check again, just in case
            aspect_ratio = width / height
            new_width = self.videoLabel.width()
            new_height = int(new_width / aspect_ratio)
            
            # Resize the image
            image = cv2.resize(image, (new_width, new_height))
            
            # Create QImage with the correct format and stride
            qimage = QImage(image.data, image.shape[1], image.shape[0], image.shape[1] * 3, QImage.Format.Format_RGB888)
            
            # Convert to QPixmap for display
            frameImagePixmap = QPixmap.fromImage(qimage)
            return frameImagePixmap


    def setup_playback(self, audio_url, thumbnail_url, info_dict, loadingMsg):
        # Set pixmap to the thumbnail_url
        self.thumbnail = self.get_thumbnail(thumbnail_url)
        self.currentScreen = self.videoLabel
        self.videoLabel.setPixmap(self.thumbnail)

        ### Audio setup
        self.audio_streamer.set_youtube_url(audio_url)
        signal.signal(signal.SIGINT, self.audio_streamer.handle_signal)  # Handle CTRL+C
        self.audio_streamer.start_stream()
        
        ### Lyric setup
        lyrics = None
        title = info_dict['title']
        artist = info_dict['artist'] if type(info_dict['artist']) == str else info_dict['artist'][0]
        print(f"Searching for lyrics for {title} by {artist}")
        try:
            lyrics = syncedlyrics.search(f"[{title}] [{artist}]", enhanced=True)
        except:
            lyrics = None

        if not lyrics:
            lyrics = 'No lyrics found'
        else:
            with open('lyrics.txt', 'w', encoding='utf-8') as f:
                f.write(lyrics)

            self.isRenderingLyrics = True
            lyrics = LRCParser(lyrics)
            lyrics.parse(word_level=self.word_level_lyrics)

            self.lyrics = [(line.timestamp_ms, line.text) for line in lyrics.get_lines()]
            self.lyricIndex = 0
            self.lyricsTimer.start()
            self.updateLyrics()
        
        self.isPaused = False
        loadingMsg.accept()

    def onSearchButtonClick(self):
        if self.audio_streamer:
            self.audio_streamer.cleanup()
            if self.lyricsTimer:
                self.lyricsTimer.stop()
            self.isRenderingLyrics = False
            self.isRenderingVideo = False
            self.isPaused = False
            self.lyricIndex = 0
            self.lyrics = None


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

    def togglePlayPause(self):
        if self.isPaused:
            self.audio_streamer.play()
            self.isRenderingVideo = True
            if self.videoTimer is not None:
                self.videoTimer.start()
            if self.lyricsTimer is not None:
                self.lyricsTimer.start()
            
            self.isPaused = False

        else:
            self.audio_streamer.pause()
            self.isRenderingVideo = False
            if self.videoTimer is not None:
                self.videoTimer.stop()
            if self.lyricsTimer is not None:
                self.lyricsTimer.stop()
            
            self.isPaused = True



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
            outlineWidth = 2  # Adjust the pen width to the outline thickness
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
    # window.audio_streamer.cleanup()
    if window.mainScreen.audio_streamer:
        window.mainScreen.audio_streamer.cleanup()
    if window.mainScreen.lyricsTimer:
        window.mainScreen.lyricsTimer.stop()

    app.quit()



app = QApplication(sys.argv)
window = MainWindow()
window.show()
app.aboutToQuit.connect(handleClose)
app.exec()

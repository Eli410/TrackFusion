import sys
import re
import cv2
import ytm
import imageio.v3 as iio
from math import floor
from PyQt6.QtWidgets import (QWidget, QLabel, QApplication, QLineEdit, QTextEdit, QVBoxLayout, 
                             QHBoxLayout, QPushButton, QCheckBox, QStyledItemDelegate, QCompleter,
                             QMessageBox,)
from PyQt6.QtCore import QTimer, QSize, Qt, QRect, QStringListModel, QThread, pyqtSignal, QObject
from PyQt6.QtGui import QPixmap, QImage, QColor, QFont
from ytdl import get_audio_and_thumbnail
import syncedlyrics
import signal
from streamer import AudioStreamer
import shutil
import os
import traceback

model = 'hdemucs_mmi'

class MainWindow(QWidget):
    def __init__(self):
        super().__init__()

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
        searchLayout.addWidget(self.searchBar)

        self.searchButton = QPushButton(self)
        self.searchButton.setText("Play")
        self.searchButton.setFixedWidth(75)
        self.searchButton.setFixedHeight(50)
        self.searchButton.clicked.connect(self.onSearchButtonClick)
        searchLayout.addWidget(self.searchButton)

        self.timer = QTimer(self)
        self.timer.setInterval(800)
        self.timer.setSingleShot(True)
        self.timer.timeout.connect(self.show_completer)



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

        lyricFowardButton = QPushButton(self)
        lyricFowardButton.setText("+ 0.5")
        lyricFowardButton.setFixedWidth(75)
        lyricFowardButton.setFixedHeight(50)
        lyricFowardButton.clicked.connect(self.adjustLyrics)

        lyricBackwardButton = QPushButton(self)
        lyricBackwardButton.setText("- 0.5")
        lyricBackwardButton.setFixedWidth(75)
        lyricBackwardButton.setFixedHeight(50)
        lyricBackwardButton.clicked.connect(self.adjustLyrics)

        lyricButtonsLayout = QHBoxLayout()
        lyricButtonsLayout.addWidget(lyricBackwardButton)
        lyricButtonsLayout.addWidget(lyricFowardButton)

        lyricBoxLayout.addWidget(self.lyricBox)
        lyricBoxLayout.addLayout(lyricButtonsLayout)
        
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

        if self.audio_streamer:
            self.audio_streamer.change_tracks(options)

    def onSearchButtonClick(self):
        if self.audio_streamer:
            self.audio_streamer.stop()
            self.audio_streamer = None
        
        # reset all comboboxes
        self.checkbox1.setChecked(True)
        self.checkbox2.setChecked(True)
        self.checkbox3.setChecked(True)
        self.checkbox4.setChecked(True)


        youTubeLinkRegex = re.compile(r'^(https?://)?(www\.)?(youtube\.com|youtu\.be)/(watch\?v=|embed/|v/)?([A-Za-z0-9_-]{11})(&.*)*$') #Test Later

        if (youTubeLinkRegex.fullmatch(self.searchBar.text())):
            audio_url, thumbnail_url, info_dict = get_audio_and_thumbnail(self.searchBar.text())

            # Set pixmap to the thumbnail_url
            image = iio.imread(thumbnail_url)
            print(thumbnail_url)
            height, width, _ = image.shape
            aspect_ratio = width / height
            new_height = 540
            new_width = int(new_height * aspect_ratio)
            image = cv2.resize(image, (new_width, new_height))
            qimage = QImage(image.data, image.shape[1], image.shape[0], QImage.Format.Format_RGB888)
            frameImagePixmap = QPixmap.fromImage(qimage)
            self.videoLabel.setPixmap(frameImagePixmap)

            ### Audio setup
            self.audio_streamer = AudioStreamer(audio_url)
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
                self.lyricBox.setText(lyrics)
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
                self.updateLyrics()
                self.lyricsTimer.start()  # Start lyrics timer
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
        if self.lyricIndex == len(self.lyrics) - 1:
            self.lyricBox.setHtml("<b>" + self.lyrics[self.lyricIndex][1] + "</b>" + "<br>" + "<br>")
        elif self.lyricIndex == len(self.lyrics) - 2:
            self.lyricBox.setText("<b>" + self.lyrics[self.lyricIndex][1] + "</b>" + "<br>" + "<br>" +
                                  self.lyrics[self.lyricIndex+1][1] + "<br>" + "<br>")
        else: 
            self.lyricBox.setText("<b>" + self.lyrics[self.lyricIndex][1] + "</b>" + "<br>" + "<br>" +
                                  self.lyrics[self.lyricIndex+1][1] + "<br>" + "<br>" +
                                  self.lyrics[self.lyricIndex+2][1] + "<br>" + "<br>")

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
                suggestion = self.ytm_api.search_videos(text)['items'][:5]
                suggestion += (self.ytm_api.search_songs(text)['items'][:5])
            except Exception as e:
                print(f"Error searching for songs: {e}")
                self.ytm_api = ytm.YouTubeMusic()
                suggestion = []
        
            suggestions = []
            for song in suggestion:
                song_name = song.get('name')
                artist_name = song.get('artists', [{}])[0].get('name')
                display_text = f"{song_name} - {artist_name}" if artist_name else song_name
                suggestions.append((display_text, song.get('videoId', song.get('id'))))
            self.model.set_data(suggestions)
            self.completer.complete()
            


class AutocompleteDelegate(QStyledItemDelegate):
    def __init__(self, parent=None):
        super().__init__(parent)

    def paint(self, painter, option, index):
        super().paint(painter, option, index)
        painter.save()

        # Retrieve data
        text = index.data(Qt.ItemDataRole.DisplayRole)

        # Define the rectangle for the text
        text_rect = QRect(
            option.rect.left() + 5,
            option.rect.top(),
            option.rect.width() - 10,
            option.rect.height(),
        )

        # Draw the text
        painter.setFont(QFont("Arial", 10))
        painter.drawText(text_rect, Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignLeft, text)

        painter.restore()

    def sizeHint(self, option, index):
        return QSize(200, 50)

class AutocompleteModel(QStringListModel):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.suggestions = [] 

    def populate_model(self):
        display_strings = [s[0] for s in self.suggestions]
        self.setStringList(display_strings)

    def data(self, index, role):
        if not index.isValid():
            return None
        if role == Qt.ItemDataRole.DisplayRole:
            return self.suggestions[index.row()][0]
        if role == Qt.ItemDataRole.UserRole:
            pixmap = QPixmap(self.suggestions[index.row()][1])
            if pixmap.isNull():
                return None
            return pixmap
        return super().data(index, role)

    def set_data(self, suggestions):
        self.suggestions = suggestions
        self.populate_model()
    
    
def handleClose():
    if window.audio_streamer:
        window.audio_streamer.stop()
    if window.videoTimer:
        window.videoTimer.stop()
    if window.lyricsTimer:
        window.lyricsTimer.stop()
    app.quit()



app = QApplication(sys.argv)
window = MainWindow()
window.show()
app.aboutToQuit.connect(handleClose)
app.exec()

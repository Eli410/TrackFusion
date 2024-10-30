from PyQt6.QtWidgets import (QWidget, QLabel, QApplication, QLineEdit, QVBoxLayout, 
                             QHBoxLayout, QPushButton, QCheckBox, QStyledItemDelegate, QCompleter,
                             QMessageBox,)
from PyQt6.QtCore import QTimer, QSize, Qt, QRect, QStringListModel, pyqtSignal, QThread
from PyQt6.QtGui import QPixmap, QImage, QColor, QFont, QPainter, QPen
from ytdl import get_audio_and_thumbnail
import traceback

class ytdl_Worker(QThread):
    finished = pyqtSignal(object, object, object, object)  # Signal to indicate completion

    def __init__(self, url, loadingMsg):
        super(ytdl_Worker, self).__init__()
        self.url = url
        self.loadingMsg = loadingMsg

    def run(self):
        try:
            audio_url, thumbnail_url, info_dict = get_audio_and_thumbnail(self.url)
            self.finished.emit(audio_url, thumbnail_url, info_dict, self.loadingMsg)
        except Exception as e:
            print(f"Error getting audio and thumbnail: {e}")
            traceback.print_exc()
            self.finished.emit(None, None, None, self.loadingMsg)

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

class VideoWindow(QLabel):
    clicked = pyqtSignal()  # Signal for click events
    hovered = pyqtSignal(bool)  # Signal for hover events, bool indicates hover state

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setStyleSheet("""
            QLabel {
                border: 4px solid gray;
                border-radius: 10px;
            }
        """)
        self.setMouseTracking(True)  # Important to detect mouse hover when no button is pressed

    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            self.clicked.emit()  # Emit the clicked signal on left mouse button press

    def enterEvent(self, event):
        self.hovered.emit(True)  # Emit the hovered signal with True when mouse enters the label

    def leaveEvent(self, event):
        self.hovered.emit(False)  # Emit the hovered signal with False when mouse leaves the label




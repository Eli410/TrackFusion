from PyQt6.QtWidgets import (QWidget, QLabel, QComboBox, QLineEdit, QVBoxLayout, 
                             QHBoxLayout, QPushButton, QCheckBox, QStyledItemDelegate, QCompleter,
                             QMessageBox, QFileDialog, QProgressDialog)
from PyQt6.QtCore import QObject, QSize, Qt, QRect, QStringListModel, pyqtSignal, QThread
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

class ExportWorker(QObject):
    finished = pyqtSignal()

    def __init__(self, export_func, selected_checkboxes, selected_format, export_path):
        super().__init__()
        self.export_func = export_func
        self.selected_checkboxes = selected_checkboxes
        self.selected_format = selected_format
        self.export_path = export_path

    def run(self):
        self.export_func(self.selected_checkboxes, self.selected_format, self.export_path)
        self.finished.emit()

class ExportPopup(QWidget):
    def __init__(self, tracks, export_func, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Export Options")
        self.setGeometry(100, 100, 300, 200)
        self.export_func = export_func
        layout = QVBoxLayout()

        # Add checkboxes
        self.checkboxes = []
        for _checkbox in tracks:
            checkbox = QCheckBox(_checkbox.text())
            self.checkboxes.append(checkbox)
            if _checkbox.isChecked():
                checkbox.setChecked(True)
            layout.addWidget(checkbox)

        # Add format dropdown
        self.format_label = QLabel("Select Format:")
        self.format_dropdown = QComboBox()
        self.format_dropdown.addItems(["mp3", "wav", "flac", "aac"])
        layout.addWidget(self.format_label)
        layout.addWidget(self.format_dropdown)

        # Add export path picker
        self.path_label = QLabel("Export Path:")
        layout.addWidget(self.path_label)
        self.path_edit = QLineEdit()
        self.path_button = QPushButton("Browse")
        self.path_button.clicked.connect(self.browse_path)
        path_layout = QHBoxLayout()
        path_layout.addWidget(self.path_edit)
        path_layout.addWidget(self.path_button)
        layout.addLayout(path_layout)

        # Export button
        self.export_button = QPushButton("Export")
        self.export_button.clicked.connect(self.export)
        layout.addWidget(self.export_button)

        self.setLayout(layout)

    def browse_path(self):
        export_path = QFileDialog.getExistingDirectory(self, "Select Directory")
        if export_path:
            self.path_edit.setText(export_path)

    def export(self):
        selected_checkboxes = [cb.text() for cb in self.checkboxes if cb.isChecked()]
        if not selected_checkboxes:
            QMessageBox.warning(self, "Warning", "Please select at least one track to export.")
            return

        selected_format = self.format_dropdown.currentText()
        export_path = self.path_edit.text()
        if not export_path:
            QMessageBox.warning(self, "Warning", "Please select an export path.")
            return

        # Create and show the progress dialog
        self.progress_dialog = QProgressDialog("Exporting files...", "Cancel", 0, 0, self)
        self.progress_dialog.setWindowTitle("Exporting")
        self.progress_dialog.setWindowModality(Qt.WindowModality.WindowModal)
        self.progress_dialog.setCancelButton(None)  # Remove the cancel button if not needed
        self.progress_dialog.show()

        # Start export in another thread
        self.thread = QThread()
        self.worker = ExportWorker(self.export_func, selected_checkboxes, selected_format, export_path)
        self.worker.moveToThread(self.thread)
        self.thread.started.connect(self.worker.run)
        self.worker.finished.connect(self.thread.quit)
        self.worker.finished.connect(self.worker.deleteLater)
        self.thread.finished.connect(self.thread.deleteLater)
        self.worker.finished.connect(self.progress_dialog.close)
        self.thread.start()

        # Close the export popup
        self.close()

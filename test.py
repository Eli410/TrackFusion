import sys
from PyQt6.QtWidgets import QWidget, QApplication
from PyQt6.QtGui import (QPixmap, QPainter, QColor, QFont, QTextDocument,
                         QTextCursor, QTextCharFormat)
from PyQt6.QtCore import QTimer, Qt, QRectF

class LyricsRenderer(QWidget):
    """
    A PyQt5 widget that renders lyrics over an image, highlighting words
    at their specified timings.
    """
    def __init__(self, pixmap, lyrics_lines, parent=None):
        super().__init__(parent)
        self.pixmap = pixmap
        self.lyrics_lines = lyrics_lines  # List of LRCLine objects
        self.current_time_ms = 0  # Current playback time in milliseconds

        self.initUI()

    def initUI(self):
        # Set the widget size to match the pixmap size
        self.setFixedSize(self.pixmap.size())
        
        # Create a timer to update the lyrics based on time
        self.timer = QTimer(self)
        self.timer.timeout.connect(self.updateLyrics)
        self.timer.start(100)  # Update every 100 ms

    def updateLyrics(self):
        """
        Updates the current time and triggers a repaint of the widget.
        """
        # Update the current time (in a real application, synchronize with playback)
        self.current_time_ms += 100  # Simulate playback time increment by 100 ms
        self.update()  # Trigger repaint

    def paintEvent(self, event):
        """
        Paints the background image and the current lyrics line onto the widget.
        """
        painter = QPainter(self)
        # Draw the background image
        painter.drawPixmap(0, 0, self.pixmap)

        # Determine the current line based on the current time
        current_line = None
        for line in self.lyrics_lines:
            if line.timestamp_ms <= self.current_time_ms:
                current_line = line
            else:
                break

        # Render the current line if available
        if current_line:
            self.renderLine(painter, current_line)

    def renderLine(self, painter, line):
        """
        Renders a single line of lyrics onto the widget.
        """
        font = QFont('Arial', 32)
        font.setBold(True)
        painter.setFont(font)

        # Set up a QTextDocument to handle complex text rendering
        document = QTextDocument()
        document.setDefaultFont(font)
        cursor = QTextCursor(document)

        # Prepare to draw text with a black outline (stroke)
        outline_pen = QColor('black')
        fill_pen = QColor('white')
        highlight_pen = QColor('blue')

        # Split the text into words
        words = line.text.split()
        idx = 0

        for word in words:
            # Get the word-level timestamp if available
            if idx < len(line.word_timings):
                word_timestamp_ms, _ = line.word_timings[idx]
            else:
                word_timestamp_ms = line.timestamp_ms  # Use line timestamp as fallback

            # Determine the color based on whether the word's time has come
            if word_timestamp_ms <= self.current_time_ms:
                text_color = highlight_pen  # Highlighted word
            else:
                text_color = fill_pen  # Default color

            # Set up the text format with stroke and fill
            text_format = QTextCharFormat()
            text_format.setForeground(text_color)

            # Insert the word with the specified format
            cursor.insertText(word + ' ', text_format)
            idx += 1

        # Calculate the position to render the text (centered at the bottom)
        layout_width = document.size().width()
        rect = self.rect()
        x = (rect.width() - layout_width) / 2
        y = rect.height() - 100  # Position 100 pixels from the bottom

        # Draw the text outline by drawing the text multiple times offset by one pixel
        painter.save()
        painter.translate(x, y)
        for dx in [-1, 0, 1]:
            for dy in [-1, 0, 1]:
                if dx == 0 and dy == 0:
                    continue  # Skip the center (we'll draw it later)
                painter.setPen(outline_pen)
                painter.translate(dx, dy)
                document.drawContents(painter)
                painter.translate(-dx, -dy)
        # Draw the text fill
        painter.setPen(fill_pen)
        document.drawContents(painter)
        painter.restore()

    def sizeHint(self):
        """
        Suggests a size for the widget.
        """
        return self.pixmap.size()

# The LRCLine class from the previous implementation
class LRCLine:
    def __init__(self, timestamp_ms, text, word_timings=None):
        self.timestamp_ms = timestamp_ms
        self.text = text
        self.word_timings = word_timings or []

# Example usage
if __name__ == '__main__':
    app = QApplication(sys.argv)

    # Load an image to use as the background
    pixmap = QPixmap('images.png')  # Replace with your image path

    # Create example lyrics lines (would be parsed from LRCParser in practice)
    lyrics_lines = [
        LRCLine(
            timestamp_ms=0,
            text='You (you), you are (you are) my universe',
            word_timings=[
                (0, 'You'),
                (500, '(you),'),
                (1000, 'you'),
                (1500, 'are'),
                (2000, '(you'),
                (2500, 'are)'),
                (3000, 'my'),
                (3500, 'universe')
            ]
        )
    ]

    # Create the lyrics renderer widget
    renderer = LyricsRenderer(pixmap, lyrics_lines)
    renderer.show()

    sys.exit(app.exec())


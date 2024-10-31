import re
from typing import List, Optional

class LRCLine:
    """
    A class representing a single line of LRC lyrics with timestamp and text.
    """
    def __init__(self, timestamp_ms: int, text: str, word_timings: Optional[List[tuple]] = None):
        self.timestamp_ms = timestamp_ms  # Line-level timestamp in milliseconds
        self.text = text                  # Lyrics text
        self.word_timings = word_timings or []  # List of tuples (word_timestamp_ms, word)

    def __repr__(self):
        return f"LRCLine(timestamp_ms={self.timestamp_ms}, text='{self.text}', word_timings={self.word_timings})"

class LRCParser:
    """
    A custom parser for LRC lyrics.
    """
    def __init__(self, lyrics: str):
        self.lyrics = lyrics
        self.lines: List[LRCLine] = [LRCLine(0, '')]

    def parse(self, word_level: bool = False):
        """
        Parses the LRC lyrics.

        Parameters:
            word_level (bool): If True, parses word-level timings.
                               If False, removes word-level timestamps.
        """
        # Split the lyrics into individual lines
        for line in self.lyrics.strip().split('\n'):
            # Check if the line has a valid line-level timestamp
            line_match = re.match(r'\[(\d{2}):(\d{2}\.\d{2})\](.*)', line)
            if line_match:
                minutes, seconds, content = line_match.groups()
                # Convert line-level timestamp to milliseconds
                line_timestamp_ms = int(minutes) * 60000 + float(seconds) * 1000

                if word_level:
                    # Parse word-level timings
                    word_timings = self._parse_word_timings(content)
                    # Remove word-level timestamps from the text
                    clean_text = re.sub(r'<\d{2}:\d{2}\.\d{2}>', '', content).strip()
                    lrc_line = LRCLine(timestamp_ms=int(line_timestamp_ms), text=clean_text, word_timings=word_timings)
                else:
                    # Remove word-level timestamps
                    clean_text = re.sub(r'<\d{2}:\d{2}\.\d{2}>', '', content).strip()
                    lrc_line = LRCLine(timestamp_ms=int(line_timestamp_ms), text=clean_text)

                self.lines.append(lrc_line)
            else:
                # Ignore lines without valid format
                continue

    def _parse_word_timings(self, content: str) -> List[tuple]:
        """
        Parses word-level timings from the content.

        Parameters:
            content (str): The lyrics content with word-level timestamps.

        Returns:
            List[tuple]: A list of tuples containing word timestamps and words.
        """
        # Regex pattern to find word-level timestamps and words
        pattern = r'(<\d{2}:\d{2}\.\d{2}>)([^<]+)'
        matches = re.findall(pattern, content)

        word_timings = []
        for time_tag, word in matches:
            # Extract timestamp from time_tag
            time_match = re.match(r'<(\d{2}):(\d{2}\.\d{2})>', time_tag)
            if time_match:
                minutes, seconds = time_match.groups()
                # Convert word-level timestamp to milliseconds
                word_timestamp_ms = int(minutes) * 60000 + float(seconds) * 1000
                word = word.strip()
                word_timings.append((int(word_timestamp_ms), word))

        return word_timings

    def shift(self, ms: int):
        """
        Shifts all line-level timestamps by the specified amount of milliseconds.

        Parameters:
            ms (int): The amount of milliseconds to shift timestamps by.
                      Can be positive or negative.
        """
        for line in self.lines:
            # Shift line-level timestamp
            line.timestamp_ms += ms
            # Ensure timestamp is not negative
            if line.timestamp_ms < 0:
                line.timestamp_ms = 0

            # Shift word-level timestamps if they exist
            if line.word_timings:
                shifted_word_timings = []
                for word_timestamp_ms, word in line.word_timings:
                    new_word_timestamp_ms = word_timestamp_ms + ms
                    # Ensure timestamp is not negative
                    if new_word_timestamp_ms < 0:
                        new_word_timestamp_ms = 0
                    shifted_word_timings.append((new_word_timestamp_ms, word))
                line.word_timings = shifted_word_timings

    def get_lines(self) -> List[LRCLine]:
        """
        Returns the parsed lines.

        Returns:
            List[LRCLine]: A list of parsed LRCLine objects.
        """
        return self.lines


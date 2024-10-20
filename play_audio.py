import os
import pyaudio
import numpy as np
import soundfile as sf
import subprocess
import shutil
import threading
import time

class AudioStreamer:
    def __init__(self, source, root_dir):
        self.tracks = [
            # "vocals",
            'no_vocals',
        ]
        self.source = source
        self.root_dir = root_dir
        self.p = pyaudio.PyAudio()
        self.stream = None
        self.i = 0  # Chunk index
        self.playing = threading.Event()
        self.playing.set()  # Start in playing state
        self.stop_event = threading.Event()
        self.thread = threading.Thread(target=self._stream_audio)
        self.thread.daemon = True  # Ensure thread exits when main program exits
        self.child = None  # To hold the processing subprocess

        # Variables for tracking playback time
        self.playback_start_time = None  # Time when playback started
        self.pause_start_time = None  # Time when playback was paused
        self.total_paused_time = 0.0  # Total time paused
        self.lock = threading.Lock()  # Lock for thread-safe operations

    def start_processing(self):
        os.makedirs(self.root_dir, exist_ok=True)
        self.child = subprocess.Popen(["python", "processing.py", self.source], stderr=subprocess.PIPE, stdout=subprocess.PIPE)

    def read_audio_file(self, file_path):
        """Reads an audio file and returns numpy array and sample rate"""
        data, samplerate = sf.read(file_path)
        return data, samplerate

    def _stream_audio(self):
        """Internal method to stream audio in a separate thread."""
        # Wait until the first chunk is available
        while not (os.path.exists(f"{self.root_dir}/chunk_{self.i}") and len(os.listdir(f"{self.root_dir}/chunk_{self.i}")) == 3):
            if self.stop_event.is_set():
                return
            time.sleep(0.1)

        with self.lock:
            self.playback_start_time = time.time() + 0.5 

        while True:
            if self.stop_event.is_set():
                break
            try:
                # Handle play/pause
                while not self.playing.is_set():
                    with self.lock:
                        if self.pause_start_time is None:
                            self.pause_start_time = time.time()
                    if self.stop_event.is_set():
                        break
                    time.sleep(0.1)

                if self.pause_start_time:
                    with self.lock:
                        paused_duration = time.time() - self.pause_start_time
                        self.total_paused_time += paused_duration
                        self.pause_start_time = None

                # Load and overlay each track in the tracks list
                combined = None
                sample_rate = None
                for track in self.tracks:
                    file_path = f"{self.root_dir}/chunk_{self.i}/{track}.mp3"
                    audio_data, sr = self.read_audio_file(file_path)
                    if combined is None:
                        combined = audio_data
                        sample_rate = sr
                    else:
                        combined += audio_data
                # Normalize the combined audio to prevent clipping
                combined = combined / np.max(np.abs(combined), axis=0)
                # If the stream hasn't started, initialize it
                if self.stream is None:
                    self.stream = self.p.open(format=self.p.get_format_from_width(2),  # Assuming 16-bit audio
                                            channels=combined.shape[1] if len(combined.shape) > 1 else 1,
                                            rate=sample_rate,
                                            output=True)
                # Convert numpy array to int16
                combined_int16 = (combined * 32767).astype(np.int16)

                # Determine the number of channels
                if len(combined_int16.shape) == 1:
                    num_channels = 1
                else:
                    num_channels = combined_int16.shape[1]

                num_samples = combined_int16.shape[0]
                frame_size = 1024  # Number of samples per frame

                for start_idx in range(0, num_samples, frame_size):
                    end_idx = min(start_idx + frame_size, num_samples)
                    frame = combined_int16[start_idx:end_idx]

                    # Handle play/pause
                    while not self.playing.is_set():
                        with self.lock:
                            if self.pause_start_time is None:
                                self.pause_start_time = time.time()
                        if self.stop_event.is_set():
                            break
                        time.sleep(0.01)  # Smaller sleep for more responsive pause

                    if self.stop_event.is_set():
                        break

                    if self.pause_start_time:
                        with self.lock:
                            paused_duration = time.time() - self.pause_start_time
                            self.total_paused_time += paused_duration
                            self.pause_start_time = None

                    # Convert frame to bytes
                    frame_bytes = frame.tobytes()

                    # Play the frame
                    self.stream.write(frame_bytes)

                with self.lock:
                    # If playback was paused during the chunk, adjust the playback_start_time
                    if self.pause_start_time:
                        paused_duration = time.time() - self.pause_start_time
                        self.total_paused_time += paused_duration
                        self.pause_start_time = None
                    self.i += 1
            except FileNotFoundError:
                break
            except Exception as e:
                print(f"Error while streaming audio: {e}")
                break
        # Stop and close the stream
        if self.stream is not None:
            self.stream.stop_stream()
            self.stream.close()
        self.p.terminate()


    def get_pos(self):
        """Returns the current playback position in milliseconds."""
        with self.lock:
            if self.playback_start_time is None:
                return 0.0
            current_time = time.time()
            if self.playing.is_set():
                elapsed_time = current_time - self.playback_start_time - self.total_paused_time
            else:
                # If paused, don't include the current paused duration
                elapsed_time = self.pause_start_time - self.playback_start_time - self.total_paused_time
            position_ms = elapsed_time * 1000.0
        return max(0.0, position_ms)

    def play(self):
        """Resume playback."""
        with self.lock:
            if not self.playing.is_set():
                self.playing.set()
                if self.pause_start_time:
                    paused_duration = time.time() - self.pause_start_time
                    self.total_paused_time += paused_duration
                    self.pause_start_time = None

    def pause(self):
        """Pause playback."""
        print(self.lock)
        with self.lock:
            if self.playing.is_set():
                self.playing.clear()
                self.pause_start_time = time.time()

    def start(self):
        """Start processing and streaming."""
        self.start_processing()
        self.thread.start()

    def stop(self):
        """Stop processing and streaming."""
        self.stop_event.set()
        self.thread.join()
        if self.child is not None:
            self.child.terminate()
            self.child.wait()
        shutil.rmtree(self.root_dir)
        self.p.terminate()

    def handle_signal(self, signum, frame):
        """Handle incoming signals like SIGINT."""
        print("Signal received, stopping.")
        self.stop()


if __name__ == "__main__":
    source = "temp/The Weeknd, Playboi Carti - Timeless.mp3"
    directory_path = f"temp/hdemucs_mmi"

    audio_streamer = AudioStreamer(source, directory_path)
    try:
        audio_streamer.start()
        while True:
            input("Press Enter to pause/resume playback.")
            if audio_streamer.playing.is_set():
                audio_streamer.pause()
            else:
                audio_streamer.play()

    except Exception as e:
        print(e)
    finally:
        audio_streamer.stop()

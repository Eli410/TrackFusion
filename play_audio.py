import os
import pyaudio
import numpy as np
import soundfile as sf
import subprocess
import shutil
import threading
import time
import traceback
from processing import overlap
import sys
class AudioStreamer:
    def __init__(self, source, root_dir):
        self.tracks = [
            'drums',
            'bass',
            'other',
            "vocals",
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
        self.child = subprocess.Popen([sys.executable, "processing.py", self.source])#, stderr=subprocess.PIPE, stdout=subprocess.PIPE)


    def read_audio_file(self, file_path):
        """Reads an audio file and returns numpy array and sample rate"""
        data, samplerate = sf.read(file_path)
        return data, samplerate
        

    def _stream_audio(self):
        print("Streaming audio...")
        """Internal method to stream audio in a separate thread."""
        # Wait until the first chunk is available
        while not (os.path.exists(f"{self.root_dir}/chunk_{self.i}") and len(os.listdir(f"{self.root_dir}/chunk_{self.i}")) == 5):
            if self.stop_event.is_set():
                return
            time.sleep(0.1)

        with self.lock:
            self.playback_start_time = time.time() + 1

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

                # Load and store each track in the tracks list
                track_data = {}
                sample_rate = None
                num_channels = None
                chunk_path = f"{self.root_dir}/chunk_{self.i}"
                if not os.path.exists(chunk_path):
                    # Wait for the chunk to be available
                    while not os.path.exists(chunk_path):
                        if self.stop_event.is_set():
                            break
                        time.sleep(0.1)
                for track_file in os.listdir(chunk_path):
                    track_name = track_file.split('.')[0]
                    file_path = f"{chunk_path}/{track_file}"
                    audio_data, sr = self.read_audio_file(file_path)
                    track_data[track_name] = audio_data
                    if sample_rate is None:
                        sample_rate = sr
                    if num_channels is None:
                        num_channels = audio_data.shape[1] if len(audio_data.shape) > 1 else 1

                # Clean up chunk directory
                shutil.rmtree(chunk_path)

                # Prepare for frame playback
                num_samples = next(iter(track_data.values())).shape[0]
                frame_size = 1024

                # Calculate 100 ms in samples
                samples_to_skip = int(((overlap + 25) / 1000) * sample_rate)  # 100 ms of samples to skip at the start and end

                if self.stream is None:
                    self.stream = self.p.open(format=self.p.get_format_from_width(2),  # Assuming 16-bit audio
                                            channels=num_channels,
                                            rate=sample_rate,
                                            output=True)

                # Adjust loop to skip 100 ms at the beginning and the end
                start_sample = samples_to_skip
                end_sample = num_samples - samples_to_skip

                for start_idx in range(start_sample, end_sample, frame_size):
                    end_idx = min(start_idx + frame_size, end_sample)
                    with self.lock:
                        current_tracks = self.tracks.copy()  # Copy current tracks
                    # Combine the audio data for current frame
                    frame = None
                    for track in current_tracks:
                        if track in track_data:
                            track_frame = track_data[track][start_idx:end_idx]
                            if frame is None:
                                frame = track_frame.copy()
                            else:
                                frame += track_frame
                    if frame is None:
                        # If no tracks are selected, play silence
                        frame = np.zeros((end_idx - start_idx, num_channels))

                    gain_reduction = 0.8  # Reduce volume by 20%
                    frame *= gain_reduction

                    # Convert frame to int16
                    frame_int16 = (frame * 32767).astype(np.int16)

                    # Handle play/pause as before
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
                    frame_bytes = frame_int16.tobytes()
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
                print(traceback.format_exc())
                break
        # Stop and close the stream
        if self.stream is not None:
            self.stream.stop_stream()
            self.stream.close()
        self.p.terminate()



    def change_tracks(self, tracks):
        """Change the tracks to be streamed."""
        self.tracks = tracks

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
    source = "testing_files/lYBUbBu4W08.mp3"
    directory_path = f"temp/hdemucs_mmi"

    try:
        audio_streamer = AudioStreamer(source, directory_path)
        audio_streamer.start()
    except Exception as e:
        print(f"Error starting audio streamer: {e}")
        audio_streamer.stop()

    while True:
        try:
            time.sleep(1)
        except KeyboardInterrupt:
            audio_streamer.stop()
            break
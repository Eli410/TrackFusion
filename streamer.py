import yt_dlp
import pyaudio
import threading
import numpy as np
import subprocess
import queue
import time
from pathlib import Path
import torch as th
from demucs.apply import apply_model, BagOfModels
from demucs.htdemucs import HTDemucs
from demucs.pretrained import get_model, ModelLoadingError
from dora.log import fatal
import torch
import numpy as np

def process(
    audio_array: np.ndarray,
    track: str = None,
    verbose=False,
    out=Path("separated"),
    model = None,
    filename="{track}/{stem}.{ext}",
    device=None,
    shifts=1,
    overlap=0.25,
    split=True,
    segment=None,
    stem=None,
    int24=False,
    float32=False,
    clip_mode="rescale",
    flac=False,
    mp3=False,
    mp3_bitrate=320,
    mp3_preset=2,
    jobs=0,
):
    
    device = device or ("cuda" if th.cuda.is_available() else "cpu")

    try:
        # if model is None:
        #     model = get_model('htdemucs')
        model = get_model(model)  
    except ModelLoadingError as error:
        fatal(error.args[0])

    
    max_allowed_segment = float('inf')
    if isinstance(model, HTDemucs):
        max_allowed_segment = float(model.segment)
    elif isinstance(model, BagOfModels):
        max_allowed_segment = model.max_allowed_segment
    if segment is not None and segment > max_allowed_segment:
        fatal("Cannot use a Transformer model with a longer segment "
              f"than it was trained for. Maximum segment is: {max_allowed_segment}")

    if isinstance(model, BagOfModels):
        print(f"Selected model is a bag of {len(model.models)} models. "
              "You will see that many progress bars per track.")

    model.cpu()
    model.eval()

    if stem is not None and stem not in model.sources:
        fatal(
            'error: stem "{stem}" is not in selected model. STEM must be one of {sources}.'.format(
                stem=stem, sources=', '.join(model.sources)))

    # Reshape the audio array to stereo format
    audio_tensor = torch.from_numpy(audio_array.copy()).view(-1, 2)    
    audio_tensor = audio_tensor.float()
    wav = audio_tensor.t()


    wav /= 32768.0  # Scale int16 audio data to the range [-1, 1]


    sources = apply_model(model, wav[None], device=device, shifts=shifts,
                        split=split, overlap=overlap, progress=True,
                        num_workers=jobs, segment=segment)[0]

    out = {}
    
    for source, name in zip(sources, model.sources):
        # Transpose and convert to NumPy array
        track = source.transpose(0, 1).cpu().numpy()
        
        #clip
        track = np.clip(track, -1, 1)

        track *= 0.8

        track = (track * 32767).astype(np.int16).flatten()

        # Assign the processed track to the output dictionary
        out[name] = track

    return out


class AudioStreamer:
    def __init__(self, model='htdemucs'):
        """
        Initializes the AudioStreamer with the given YouTube URL and processing model.
        
        Args:
            youtube_url (str): The URL of the YouTube video to stream.
            model (str): The initial model to use for audio processing.
        """
        self.youtube_url = None
        self.model = model

        self.selected_tracks = list(get_model(model).sources)
        self.audio_queue = queue.Queue()
        self.processed_audio = []  
        self.pause_event = threading.Event()
        self.pause_event.set()  # Start in paused state
        self.stop_event = threading.Event()
        self.lock = threading.Lock()  # To protect shared resources
        # self.start_time = None
        self.process = None
        self.producer_thread = None
        self.consumer_thread = None
        self.new_data_event = threading.Event()
        self.playback_position = 0 
        self.progress = 0
        self.producer_finished = False
        self.start_time = None
        self.samples_per_second = 44100
        self.channels = 2
        self.bytes_per_sample = 2  # 16-bit PCM
        self.full_played_audio = []
        # Initialize timing variables
        self.samples_per_second = 44100
        self.channels = 2
        self.bytes_per_sample = 2  # 16-bit PCM
        self.bytes_per_second = self.samples_per_second * self.channels * self.bytes_per_sample  # 176400 bytes
        self.chunk_size = self.bytes_per_second * 10  # 10 seconds of audio

        self.samples_per_ms_exact = self.samples_per_second / 1000  # 44.1 samples per ms
        self.bytes_per_ms_exact = self.samples_per_ms_exact * self.channels * self.bytes_per_sample  # 176.4 bytes per ms

        self.processed_audio_buffer = bytearray()  # Buffer to accumulate playback data
        self.buffer = bytearray() 
    def set_youtube_url(self, youtube_url):
        """
        Sets the YouTube URL for the audio stream.
        
        Args:
            youtube_url (str): The URL of the YouTube video to stream.
        """
        self.youtube_url = youtube_url

    def get_audio_stream(self):
        """
        Extracts the direct audio stream URL from a YouTube video using yt_dlp.
        
        Returns:
            str: The direct audio stream URL.
        """
        ydl_opts = {
            'format': 'bestaudio/best',
            'quiet': True,
            'no_warnings': True,
            'force_generic_extractor': True,
            'simulate': True,
            'noplaylist': True,
            'extract_flat': True,
        }
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info_dict = ydl.extract_info(self.youtube_url, download=False)
            audio_url = info_dict['url']

        return audio_url

    def start_stream(self):
        """
        Starts the audio streaming, processing, and playback.
        """
        if not self.youtube_url:
            return "YouTube URL not set."
            
        audio_stream_url = self.get_audio_stream()
        self.process = subprocess.Popen(
            [
                'ffmpeg',
                '-i', audio_stream_url,                                   # Input URL
                '-f', 's16le',                                            # Output format: 16-bit PCM
                '-acodec', 'pcm_s16le',                                   # Audio codec
                '-ar', '44100',                                           # Sample rate
                '-ac', '2',                                               # Number of channels
                '-af', 'volume=0.8',                                      # Adjust volume to 80%
                'pipe:1'                                                  # Output to stdout
            ],
            stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL
        )
        
        self.producer_thread = threading.Thread(target=self._producer, name="ProducerThread")
        self.consumer_thread = threading.Thread(target=self._consumer, name="ConsumerThread")
        self.producer_thread.start()
        self.consumer_thread.start()

    def set_model(self, model):
        """
        Sets the processing model for the audio stream.
        
        Args:
            model (str): The name of the processing model to use.
        """
        self.model = model
        temp = get_model(self.model)
        self.selected_tracks = list(temp.sources)
        
        
    def _producer(self):
        """
        Producer thread function: Reads 10-second chunks of audio data, processes them,
        splits into 100 ms chunks, and stores them for playback.
        """
        samples_per_second = 44100
        channels = 2
        bytes_per_sample = 2  # 16-bit PCM
        bytes_per_second = samples_per_second * channels * bytes_per_sample  # 44100 * 2 * 2 = 176400 bytes
        chunk_duration = 10  # 10 seconds
        chunk_size = bytes_per_second * chunk_duration  # 10 seconds of audio: 1,764,000 bytes

        samples_per_100ms = int(samples_per_second * 0.1)  # 4410 samples per 100 ms
        bytes_per_100ms = samples_per_100ms * channels * bytes_per_sample  # 4410 * 2 * 2 = 17,640 bytes

        while not self.stop_event.is_set():
            # Handle pause
            self.pause_event.wait()

            data = self.process.stdout.read(chunk_size)
            if not data:
                break  # End of stream

            # Ensure that data length is a multiple of bytes_per_sample * channels
            frame_size = bytes_per_sample * channels
            if len(data) % frame_size != 0:
                # Pad the data to make it aligned
                padding = frame_size - (len(data) % frame_size)
                data += b'\x00' * padding

            # Convert byte data to a NumPy array
            audio_data = np.frombuffer(data, dtype=np.int16)

            # Process the audio data
            try:
                # 'process' function should return a dictionary of tracks
                result = process(audio_data, model=self.model)  # Adjust if 'process' signature differs
            except Exception as e:
                print(f"Error during processing: {e}")
                continue

            # Split each track's data into 100 ms chunks
            track_chunks = {}
            for track_name, track_data in result.items():
                total_samples = len(track_data)
                # Calculate the number of full 100 ms chunks
                num_chunks = total_samples // samples_per_100ms
                # Truncate to full 100 ms chunks
                track_data = track_data[:num_chunks * samples_per_100ms]
                # Reshape to (num_chunks, samples_per_100ms)
                track_chunks[track_name] = track_data.reshape(num_chunks, samples_per_100ms)

            # Determine the number of 100 ms chunks available
            num_chunks = min(len(chunks) for chunks in track_chunks.values())

            for chunk_idx in range(num_chunks):
                chunk_dict = {}
                for track_name, chunks in track_chunks.items():
                    chunk = chunks[chunk_idx]
                    chunk_bytes = chunk.tobytes()
                    chunk_dict[track_name] = chunk_bytes

                # Store the chunk_dict in processed_audio
                with self.lock:
                    self.processed_audio.append(chunk_dict)
                # Notify the consumer that new data is available
                self.new_data_event.set()

        # Signal that production is done
        self.producer_finished = True
        # Notify the consumer in case it's waiting
        self.new_data_event.set()

    def _consumer(self):
        """
        Consumer thread function: Reads 100 ms chunks of processed audio data,
        mixes selected tracks, and plays it using PyAudio.
        """
        p = pyaudio.PyAudio()
        stream = p.open(format=pyaudio.paInt16,
                        channels=2,
                        rate=44100,
                        output=True,
                        frames_per_buffer=1024)

        bytes_per_second = 44100 * 2 * 2  # 44100 samples/sec * 2 channels * 2 bytes/sample
        bytes_per_100ms = int(bytes_per_second * 0.1)  # 100 ms => 17,640 bytes

        playback_buffer = bytearray()

        while not self.stop_event.is_set():
            self.buffer = playback_buffer
            with self.lock:
                if not self.processed_audio:
                    self.processed_audio = []
                if self.playback_position >= len(self.processed_audio):
                    # Release lock and wait for new data
                    self.lock.release()
                    self.new_data_event.wait(timeout=1)
                    self.new_data_event.clear()
                    self.lock.acquire()
                    continue

                # Get the next 100 ms chunk
                chunk_index = self.playback_position
                # if chunk_index >= len(self.processed_audio) and self.producer_finished:
                #     return  # End of stream
                processed_chunk = self.processed_audio[chunk_index]
                self.playback_position += 1
                selected_tracks = self.selected_tracks.copy()

            # Mix the selected tracks
            mixed_audio = None
            for track_name in selected_tracks:
                chunk_bytes = processed_chunk.get(track_name)
                if chunk_bytes is not None:
                    chunk_data = np.frombuffer(chunk_bytes, dtype=np.int16)
                    if mixed_audio is None:
                        mixed_audio = np.copy(chunk_data)  # Create a writable copy
                    else:
                        # Prevent overflow by using a higher dtype
                        mixed_audio = mixed_audio.astype(np.int32) + chunk_data.astype(np.int32)
                        # Clip to int16 range
                        np.clip(mixed_audio, -32768, 32767, out=mixed_audio)
                        mixed_audio = mixed_audio.astype(np.int16)
                else:
                    print(f"Track '{track_name}' not found in the processing result.")

            if mixed_audio is None:
                # If no tracks are selected or available, play silence
                mixed_audio = np.zeros(bytes_per_100ms // (2 * 2), dtype=np.int16)

            # Convert to bytes
            mixed_bytes = mixed_audio.tobytes()

            # Accumulate into playback_buffer
            playback_buffer.extend(mixed_bytes)

            if len(playback_buffer) >= bytes_per_100ms:
                # Extract exactly 100 ms
                playback_data = playback_buffer[:bytes_per_100ms]
                playback_buffer = playback_buffer[bytes_per_100ms:]

                # Handle pause
                self.pause_event.wait()

                if self.start_time is None:
                    self.start_time = time.time()

                self.progress += len(playback_data) / self.samples_per_second
                # Write to the stream
                stream.write(bytes(playback_data))

                # Store processed audio if needed
                if hasattr(self, 'full_played_audio'):
                    self.full_played_audio += playback_data
                else:
                    self.full_played_audio = playback_data

        # Play any remaining data in the playback_buffer
        if playback_buffer:
            stream.write(bytes(playback_buffer))

            if hasattr(self, 'full_played_audio'):
                self.full_played_audio += playback_buffer
            else:
                self.full_played_audio = playback_buffer

        # Cleanup PyAudio resources
        stream.stop_stream()
        stream.close()
        p.terminate()



    def seek(self, position_in_ms):
        """
        Seeks to the specified position in milliseconds in the processed audio.
        If the position is beyond the processed audio, the consumer will wait until data is available.
        """
        with self.lock:
            if position_in_ms < 0:
                position_in_ms = 0
            self.playback_position = position_in_ms
            # Notify the consumer in case it's waiting
            self.new_data_event.set()

    def play(self):
        """
        Starts or resumes playback.
        """
        if not self.producer_thread or not self.consumer_thread.is_alive():
            self.start_stream()
        else:
            self.pause_event.set()
            # if self.start_time is not None:
            #     self.start_time += time.time() - self.start_time
            print("Playback resumed.")

    def pause(self):
        """
        Pauses playback.
        """
        self.pause_event.clear()
        # if self.start_time is not None:
        #     self.start_time = time.time() - self.start_time
        print("Playback paused.")

    def stop(self):
        """
        Stops playback and terminates all threads and subprocesses immediately.
        """
        self.stop_event.set()
        self.pause_event.set()  # In case it's paused
        if self.process:
            self.process.terminate()
            self.process.kill()  # Ensure the process is killed immediately
            self.process.wait()

        if self.producer_thread:
            self.producer_thread.join(timeout=1)
        if self.consumer_thread:
            self.consumer_thread.join(timeout=1)
        print("Playback stopped.")

    def change_tracks(self, tracks):
        """
        Selects a track to be included in the playback mix.
        
        Args:
            tracks (List): List of track names to select.
        """
        with self.lock:
            self.selected_tracks = tracks


    def is_playing(self):
        """
        Checks if the streamer is currently playing.
        
        Returns:
            bool: True if playing, False otherwise.
        """
        return self.consumer_thread and self.consumer_thread.is_alive()

    def handle_signal(self, signum, frame):
        """Handle incoming signals like SIGINT."""
        print("Signal received, stopping.")
        self.stop()

    def get_pos(self):
        """
        Returns the current playback position in milliseconds.
        """
        with self.lock:
            return len(self.full_played_audio) / self.bytes_per_ms_exact


    def get_total_processed_length(self):
        """
        Returns the total length of the processed audio in milliseconds.
        """
        with self.lock:
            if self.processed_audio:
                return len(self.processed_audio)
            return 0

    def restart(self):
        """
        Restarts the playback from the beginning, with a fresh state.
        """
        # Stop any ongoing playback and processing
        self.stop()
        
        # Reset internal state variables
        self.processed_audio = []  
        self.full_played_audio = []
        self.playback_position = 0
        self.progress = 0
        self.producer_finished = False
        self.start_time = None
        
        # Re-initialize events
        self.stop_event = threading.Event()
        self.pause_event = threading.Event()
        self.pause_event.set()  # Start in unpaused state
        self.new_data_event = threading.Event()
        
        # Reset audio queue
        self.audio_queue = queue.Queue()
        
        # Start the stream again
        self.start_stream()

    def cleanup(self):
        """
        destroys the streamer and frees up resources
        """
        self.stop()
        self.processed_audio = None
        self.process = None
        self.producer_thread = None
        self.consumer_thread = None
        self.audio_queue = queue.Queue()
        self.stop_event = threading.Event()
        self.pause_event = threading.Event()
        self.pause_event.set()
        self.lock = threading.Lock()
        self.new_data_event = threading.Event()
        self.playback_position = 0
        self.progress = 0
        self.producer_finished = False
        self.full_played_audio = []
        self.start_time = None

        print("Streamer cleaned up.")

# Example usage:
if __name__ == "__main__":
    streamer = AudioStreamer(model = 'htdemucs_6s')
    streamer.set_youtube_url("https://www.youtube.com/watch?v=dQw4w9WgXcQ")  # Example URL
    streamer.start_stream()

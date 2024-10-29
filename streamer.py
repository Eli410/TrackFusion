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
        if model is None:
            model = get_model('htdemucs')
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

    ref = wav.mean(0)
    wav -= ref.mean()
    wav /= ref.std()

    sources = apply_model(model, wav[None], device=device, shifts=shifts,
                        split=split, overlap=overlap, progress=True,
                        num_workers=jobs, segment=segment)[0]

    out = {}
    
    for source, name in zip(sources, model.sources):
        # Transpose and convert to NumPy array
        track = source.transpose(0, 1).cpu().numpy()
        
        track = track * 0.1
        
        track = (track * 32768).astype(np.int16).flatten()
        
        # Assign the processed track to the output dictionary
        out[name] = track

    return out


class AudioStreamer:
    def __init__(self, youtube_url, model='htdemucs'):
        """
        Initializes the AudioStreamer with the given YouTube URL and processing model.
        
        Args:
            youtube_url (str): The URL of the YouTube video to stream.
            model (str): The initial model to use for audio processing.
        """
        self.youtube_url = youtube_url
        self.model = model
        self.selected_tracks = set([
            'vocals',
            'drums',
            'bass',
            'other'
            ]) 
        self.audio_queue = queue.Queue()
        self.processed_audio = None
        self.pause_event = threading.Event()
        self.pause_event.set()  # Start in paused state
        self.stop_event = threading.Event()
        self.lock = threading.Lock()  # To protect shared resources
        
        self.process = None
        self.producer_thread = None
        self.consumer_thread = None
        
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
        audio_stream_url = self.get_audio_stream()
        self.process = subprocess.Popen(
            [
                'ffmpeg',
                '-i', audio_stream_url,           # Input URL
                '-f', 's16le',                     # Output format: 16-bit PCM
                '-acodec', 'pcm_s16le',            # Audio codec
                '-ar', '44100',                    # Sample rate
                '-ac', '2',                        # Number of channels
                'pipe:1'                           # Output to stdout
            ],
            stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL
        )
        
        self.producer_thread = threading.Thread(target=self._producer, name="ProducerThread")
        self.consumer_thread = threading.Thread(target=self._consumer, name="ConsumerThread")
        self.producer_thread.start()
        self.consumer_thread.start()

    def _producer(self):
        """
        Producer thread function: Reads audio data, processes it, and enqueues it for playback in 1 ms chunks.
        """
        samples_per_second = 44100
        channels = 2
        bytes_per_sample = 2  # 16-bit PCM
        bytes_per_second = samples_per_second * channels * bytes_per_sample  # 44100 * 2 * 2 = 176400 bytes
        chunk_size = bytes_per_second * 10  # 1 second of audio

        samples_per_ms = samples_per_second // 1000  # 44 samples per ms
        bytes_per_ms = samples_per_ms * channels * bytes_per_sample  # 44 * 2 * 2 = 176 bytes

        while not self.stop_event.is_set():
            # Handle pause
            self.pause_event.wait()

            data = self.process.stdout.read(chunk_size)
            if not data:
                break  # End of stream

            # Ensure that data length is a multiple of bytes_per_sample * channels
            if len(data) % (bytes_per_sample * channels) != 0:
                # Pad the data to make it aligned
                padding = (bytes_per_sample * channels) - (len(data) % (bytes_per_sample * channels))
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

            # Split each track's data into 1 ms chunks
            track_chunks = {}
            for track_name, track_data in result.items():
                total_samples = len(track_data)
                # Calculate the number of full ms chunks
                num_ms = total_samples // samples_per_ms
                # Truncate to full ms chunks
                track_data = track_data[:num_ms * samples_per_ms]
                # Reshape to (num_ms, samples_per_ms)
                track_chunks[track_name] = track_data.reshape(num_ms, samples_per_ms)

            num_ms = min(len(chunks) for chunks in track_chunks.values())

            for ms in range(num_ms):
                ms_dict = {}
                for track_name, chunks in track_chunks.items():
                    ms_chunk = chunks[ms]
                    ms_bytes = ms_chunk.tobytes()
                    ms_dict[track_name] = ms_bytes
                self.audio_queue.put(ms_dict)

        # Signal the consumer that production is done
        self.audio_queue.put(None)

    def _consumer(self):
        """
        Consumer thread function: Dequeues processed audio data in 1 ms chunks, mixes selected tracks, and plays it using PyAudio.
        """
        p = pyaudio.PyAudio()
        stream = p.open(format=pyaudio.paInt16,
                        channels=2,
                        rate=44100,
                        output=True,
                        frames_per_buffer=1024)

        playback_chunk_duration = 0.1  # 100 milliseconds
        bytes_per_second = 44100 * 2 * 2  # 44100 samples/sec * 2 channels * 2 bytes/sample
        playback_chunk_size = int(bytes_per_second * playback_chunk_duration)  # 100 ms => 176400 * 0.1 = 17640 bytes

        bytes_per_ms = 44100 * 2 * 2 // 1000  # 176 bytes per millisecond
        chunks_per_playback = int(playback_chunk_duration * 1000)  # 100 chunks of 1 ms

        buffer = bytearray()
        playback_buffer = bytearray()

        while not self.stop_event.is_set():
            try:
                ms_dict = self.audio_queue.get(timeout=1)
            except queue.Empty:
                continue

            if ms_dict is None:
                break  # No more data to play

            # Mix the selected tracks
            mixed_audio = None
            with self.lock:
                selected_tracks = self.selected_tracks.copy()

            for track_name in selected_tracks:
                ms_bytes = ms_dict.get(track_name)
                if ms_bytes is not None:
                    ms_chunk = np.frombuffer(ms_bytes, dtype=np.int16)
                    if mixed_audio is None:
                        mixed_audio = ms_chunk.astype(np.float32)
                    else:
                        mixed_audio += ms_chunk.astype(np.float32)
                else:
                    print(f"Track '{track_name}' not found in the processing result.")

            if mixed_audio is None:
                # No tracks selected or tracks missing, use silence
                mixed_audio = np.zeros(bytes_per_ms // (2 * 2), dtype=np.float32)  # 176 bytes => 44 samples * 2 channels

            # Convert back to int16
            mixed_audio_int16 = mixed_audio.astype(np.int16)

            # Convert to bytes
            mixed_bytes = mixed_audio_int16.tobytes()

            # Accumulate into playback_buffer
            playback_buffer.extend(mixed_bytes)

            if len(playback_buffer) >= playback_chunk_size:
                # Extract exactly 100 ms
                playback_data = playback_buffer[:playback_chunk_size]
                playback_buffer = playback_buffer[playback_chunk_size:]

                # Handle pause
                self.pause_event.wait()

                # Write to the stream
                stream.write(bytes(playback_data))

                # Store processed audio if needed
                if self.processed_audio is None:
                    self.processed_audio = playback_data
                else:
                    self.processed_audio += playback_data

        # Play any remaining data in the playback_buffer
        if playback_buffer:
            stream.write(playback_buffer)

            if self.processed_audio is None:
                self.processed_audio = playback_buffer
            else:
                self.processed_audio += playback_buffer

        # Cleanup PyAudio resources
        stream.stop_stream()
        stream.close()
        p.terminate()


    def play(self):
        """
        Starts or resumes playback.
        """
        if not self.producer_thread or not self.consumer_thread.is_alive():
            self.start_stream()
        else:
            self.pause_event.set()
            print("Playback resumed.")

    def pause(self):
        """
        Pauses playback.
        """
        self.pause_event.clear()
        print("Playback paused.")

    def stop(self):
        """
        Stops playback and terminates all threads and subprocesses.
        """
        self.stop_event.set()
        self.pause_event.set()  # In case it's paused
        if self.process:
            self.process.terminate()
            self.process.wait()

        if self.producer_thread:
            self.producer_thread.join()
        if self.consumer_thread:
            self.consumer_thread.join()
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
        return self.pause_event.is_set() and not self.stop_event.is_set()

    def handle_signal(self, signum, frame):
        """Handle incoming signals like SIGINT."""
        print("Signal received, stopping.")
        self.stop()

    def get_pos(self):
        """
        Returns the current position in the audio stream.
        
        Returns:
            int: The current position in milliseconds.
        """
        if self.processed_audio is None:
            return 0
        return len(self.processed_audio) // (44100 * 2) * 1000
    
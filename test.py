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

    model_name = 'hdemucs_mmi'
    out = out / model_name
    out.mkdir(parents=True, exist_ok=True)
    print(f"Separated tracks will be stored in {out.resolve()}")

    # audio_array = np.frombuffer(data, dtype=np.int16)

    # Normalize the audio array
    # Reshape the audio array to stereo format
    audio_tensor = torch.from_numpy(audio_array.copy()).view(-1, 2)
    audio_tensor = audio_tensor.float() / 32768.0
    
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
        
        # Step 1: Reduce volume to 20%
        track = track * 0.2
        
        # Step 2: Normalize the audio to prevent clipping
        # Find the maximum absolute value in the track
        max_val = np.max(np.abs(track))
        
        # If the maximum value exceeds 1.0, normalize the track
        if max_val > 1.0:
            track = track / max_val  # Normalize to bring max amplitude to 1.0
        
        # Step 3: Convert to int16
        # Multiply by 32767 to scale to int16 range and convert data type
        track = (track * 32767).astype(np.int16).flatten()
        
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
        self.selected_tracks = set(['other']) 
        self.audio_queue = queue.Queue()
        self.pause_event = threading.Event()
        self.pause_event.set()  # Initially not paused
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
        Producer thread function: Reads audio data, processes it, and enqueues it for playback.
        """
        bytes_per_second = 44100 * 2 * 2  # 44100 samples/sec * 2 channels * 2 bytes/sample
        chunk_size = bytes_per_second * 10  # 10 seconds of audio

        while not self.stop_event.is_set():
            # Handle pause
            self.pause_event.wait()

            data = self.process.stdout.read(chunk_size)
            if not data:
                break  # End of stream

            if len(data) < chunk_size:
                # Pad the last chunk if necessary
                data += b'\x00' * (chunk_size - len(data))

            # Convert byte data to a NumPy array
            audio_data = np.frombuffer(data, dtype=np.int16).reshape(-1, 2)  # Shape: (samples, channels)

            # Flatten the array for processing
            audio_data_flat = audio_data.flatten()

            with self.lock:
                current_model = self.model
                tracks = self.selected_tracks.copy()

            # Process the audio data
            try:
                result = process(audio_data_flat, model=current_model)  # Adjust if 'main' signature differs
            except Exception as e:
                print(f"Error during processing: {e}")
                continue

            # Mix the selected tracks
            mixed_audio = np.zeros_like(audio_data_flat, dtype=np.float32)
            for track in tracks:
                track_data = result.get(track)
                if track_data is not None:
                    mixed_audio += track_data.astype(np.float32)
                else:
                    print(f"Track '{track}' not found in the processing result.")

            # Prevent clipping by normalizing if necessary
            max_val = np.max(np.abs(mixed_audio))
            if max_val > 32767:
                mixed_audio = mixed_audio * (32767 / max_val)

            # Convert back to int16
            mixed_audio_int16 = mixed_audio.astype(np.int16)

            # Convert to bytes and enqueue
            processed_bytes = mixed_audio_int16.tobytes()
            self.audio_queue.put(processed_bytes)

        # Signal the consumer that production is done
        self.audio_queue.put(None)

    def _consumer(self):
        """
        Consumer thread function: Dequeues processed audio data and plays it using PyAudio.
        """
        p = pyaudio.PyAudio()
        stream = p.open(format=pyaudio.paInt16,
                        channels=2,
                        rate=44100,
                        output=True,
                        frames_per_buffer=1024)

        while not self.stop_event.is_set():
            try:
                processed_data = self.audio_queue.get(timeout=1)
            except queue.Empty:
                continue

            if processed_data is None:
                break  # No more data to play

            # Handle pause
            self.pause_event.wait()

            stream.write(processed_data)

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

    def set_track(self, tracks):
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

# Usage Example
if __name__ == "__main__":
    youtube_url = "https://www.youtube.com/watch?v=GxldQ9eX2wo"
    streamer = AudioStreamer(youtube_url, model = 'hdemucs_mmi')
    
    # Start playback
    streamer.play()

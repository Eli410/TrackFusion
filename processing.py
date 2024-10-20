import os
from pydub import AudioSegment
import time
import sys
import demucs.separate
import ffmpeg
import soundfile as sf
import math


def process_audio_sync(filepath, model='hdemucs_mmi'):
    """
    Processes an audio file by splitting it into chunks, applying Demucs separation,
    and storing the outputs in a designated directory.

    Args:
        filepath (str): The path to the input MP3 file.
        model (str): The Demucs model name to use for separation.
    """
    if not os.path.isfile(filepath):
        print(f"Error: File '{filepath}' does not exist.")
        return

    try:
        # Load the audio file
        audio = AudioSegment.from_mp3(filepath)
        print(f"Loaded audio file '{filepath}' successfully.")
    except Exception as e:
        print(f"Failed to load audio file '{filepath}': {e}")
        return

        # Load audio file
    audio = AudioSegment.from_file(filepath)
    
    # Convert chunk length from seconds to milliseconds
    chunk_length_ms = 10 * 1000
    total_chunks = math.ceil(len(audio) / chunk_length_ms)

    for i in range(total_chunks):
        
        start = i * chunk_length_ms
        end = min((i + 1) * chunk_length_ms, len(audio))  # Avoid exceeding the length

        chunk = audio[start:end]
        chunk.export(f"chunk_{i}.mp3", format="mp3")
        print(f"Exported chunk {i} from {start}ms to {end}ms.")

    # # Loop over the audio in 10-second chunks
    # for i in range(0, len(audio), chunk_length):
    #     chunk_index = i // chunk_length
        start_time = time.time()
    #     print(f"Processing chunk {chunk_index}...")

    #     # Extract the chunk
    #     chunk = audio[i:i + chunk_length]

    #     # Create a temporary file for the chunk
        chunk_file = f"chunk_{i}.mp3"
    #     try:
    #         chunk.export(chunk_file, format="mp3", codec="libmp3lame")
    #         print(f"Exported chunk {chunk_index} to '{chunk_file}'.")
    #     except Exception as e:
    #         print(f"Failed to export chunk {chunk_index}: {e}")
    #         continue

        # Apply Demucs separation
        try:
            demucs.separate.main(["--mp3", "-o", "temp", "-n", model, '--two-stems=vocals', chunk_file])
            print(f"Applied Demucs separation on '{chunk_file}'.")
        except Exception as e:
            print(f"Demucs separation failed for chunk {i}: {e}")
            os.remove(chunk_file)  # Clean up the failed chunk file
            continue

        # Define output path
        output_chunk_dir = os.path.join(f'temp/{model}', f"chunk_{i}")
        os.makedirs(output_chunk_dir, exist_ok=True)
        output_path = os.path.join(output_chunk_dir, "original.mp3")

        # Move chunk to output path
        os.rename(chunk_file, output_path)

        elapsed_time = time.time() - start_time
        print(f"Chunk {i} processed in {elapsed_time:.2f} seconds.")
        print(f"Output Path: {output_path}\n")

if __name__ == "__main__":
    # take in the source audio file
    if len(sys.argv) < 2:
        print("Usage: python processing.py <path_to_audio_file>")
    else:
        audio_file_path = sys.argv[1]
        process_audio_sync(audio_file_path)
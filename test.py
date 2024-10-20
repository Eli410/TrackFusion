import os
import math
import time
from pydub import AudioSegment
import demucs.separate
import numpy as np

def process_audio_sync(filepath, model='hdemucs_mmi', chunk_length=10, overlap_duration=1):
    """
    Processes an audio file by splitting it into overlapping chunks, applying Demucs separation,
    and recombining the outputs with crossfading to eliminate gaps between chunks.

    Args:
        filepath (str): The path to the input MP3 file.
        model (str): The Demucs model name to use for separation.
        chunk_length (int): The length of each chunk in seconds.
        overlap_duration (int): The duration of overlap between chunks in seconds.
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

    # Convert durations from seconds to milliseconds
    chunk_length_ms = chunk_length * 1000
    overlap_ms = overlap_duration * 1000
    step_ms = chunk_length_ms - overlap_ms
    total_chunks = math.ceil((len(audio) - overlap_ms) / step_ms)


    for i in range(total_chunks):
        start = i * step_ms
        end = start + chunk_length_ms
        if end > len(audio):
            end = len(audio)
            start = max(0, end - chunk_length_ms)  # Ensure the last chunk is the correct length

        chunk = audio[start:end]
        chunk_file = f"chunk_{i}.mp3"
        chunk.export(chunk_file, format="mp3")
        print(f"Exported chunk {i} from {start}ms to {end}ms.")

        start_time = time.time()

        # Apply Demucs separation
        try:
            demucs.separate.main(["--mp3", "-o", "temp", "-n", model, chunk_file])
            print(f"Applied Demucs separation on '{chunk_file}'.")
        except Exception as e:
            print(f"Demucs separation failed for chunk {i}: {e}")
            os.remove(chunk_file)  # Clean up the failed chunk file
            continue

        # Define output path
        output_chunk_dir = os.path.join('temp', model, os.path.splitext(os.path.basename(chunk_file))[0])
        vocals_path = os.path.join(output_chunk_dir, "vocals.mp3")

        # Clean up the chunk file
        os.remove(chunk_file)

        elapsed_time = time.time() - start_time
        print(f"Chunk {i} processed in {elapsed_time:.2f} seconds.")
        print(f"Output Path: {vocals_path}\n")

    # Recombine processed chunks with crossfading
    # final_audio = processed_clips[0]
    # for i in range(1, len(processed_clips)):
    #     final_audio = final_audio.append(processed_clips[i], crossfade=overlap_ms)
    
    print("Processing complete.")


if __name__ == "__main__":
    process_audio_sync("testing_files/Queen - Don't Stop Me Now (Official Video).mp3")
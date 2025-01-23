import yt_dlp
from pathlib import Path


def get_video_info(video_id):
    # Define the yt-dlp options
    ydl_opts = {
        'skip_download': True,  # Skip the actual download of the video
        'extract_flat': 'in_playlist',  # Extract information without actually downloading
    }

    # Use yt-dlp to extract information
    with yt_dlp.YoutubeDL(ydl_opts) as ydl:
        result = ydl.extract_info(f"https://www.youtube.com/watch?v={video_id}", download=False)
        if result is None:
            return None

    return result


print(get_video_info("dQw4w9WgXcQ"))
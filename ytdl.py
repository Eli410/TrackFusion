import yt_dlp
import json


def download_video_and_audio(url, username='oauth2', password='', output_dir='.'):
    # Options for downloading the video at 720p resolution
    video_opts = {
        'username': username,
        'password': password,
        'format': 'bestvideo[height<=480][ext=mp4]',  # Download best video at 720p
        'outtmpl': f'{output_dir}/%(title)s.%(ext)s',  # Output template for video
    }

    # Options for downloading the best audio available and converting it to MP3
    audio_opts = {
        'username': username,
        'password': password,
        'format': 'bestaudio',  # Download best audio available
        'postprocessors': [{
            'key': 'FFmpegExtractAudio',  # Use FFmpeg to extract audio
            'preferredcodec': 'mp3',  # Convert audio to MP3
            'preferredquality': '192',  # Set quality (you can adjust this as needed)
        }],
        'outtmpl': f'{output_dir}/%(title)s.%(ext)s',  # Output template for audio
    }

    # Initialize yt_dlp and get video info to construct file paths
    with yt_dlp.YoutubeDL() as ydl:
        info_dict = ydl.extract_info(url, download=False)
        video_title = info_dict.get('title', 'downloaded_video')

    video_path = f"{output_dir}/{video_title}.mp4"
    audio_path = f"{output_dir}/{video_title}.mp3"

    # Download the video
    with yt_dlp.YoutubeDL(video_opts) as ydl:
        ydl.download([url])

    # Download and convert the audio
    with yt_dlp.YoutubeDL(audio_opts) as ydl:
        ydl.download([url])

    return video_path, audio_path, info_dict

# Example usage:
if __name__ == "__main__":
    video_file, audio_file = download_video_and_audio('https://www.youtube.com/watch?v=2ZBtPf7FOoM')
    print("Video file:", video_file)
    print("Audio file:", audio_file)

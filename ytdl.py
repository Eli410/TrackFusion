import yt_dlp

def download_video_and_audio(url, username='oauth2', password='', output_dir='.'):
    ydl_opts = {
        'format': 'bestvideo[height<=480]',  # Choose the best video with a maximum height of 480p
    }
    with yt_dlp.YoutubeDL(ydl_opts) as ydl:
        info_dict = ydl.extract_info(url, download=False)
        video_url = info_dict.get('url')
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
        'outtmpl': f'{output_dir}/%(id)s.%(ext)s',  # Output template for audio
    }

    # Initialize yt_dlp and get video info to construct file paths
    with yt_dlp.YoutubeDL() as ydl:
        info_dict = ydl.extract_info(url, download=False)
        video_id = info_dict.get('id', 'downloaded_video')

    
    audio_path = f"{output_dir}/{video_id}.mp3"

    # Download and convert the audio
    with yt_dlp.YoutubeDL(audio_opts) as ydl:
        ydl.download([url])

    return video_url, audio_path, info_dict

def get_audio_and_thumbnail(url):
    ydl_opts = {
        'format': 'bestaudio',  # Choose the best audio available
    }
    with yt_dlp.YoutubeDL(ydl_opts) as ydl:
        info_dict = ydl.extract_info(url, download=False)
        audio_url = info_dict.get('url')
        thumbnail_url = info_dict.get('thumbnail')

    return audio_url, thumbnail_url, info_dict

# Example usage:
if __name__ == "__main__":
    url = 'https://www.youtube.com/watch?v=dQw4w9WgXcQ'
    video_url, audio_path, info_dict = download_video_and_audio(url)
    print(f"Downloaded video URL: {video_url}")
    print(f"Downloaded audio path: {audio_path}")
    audio_url, thumbnail_url, info_dict = get_audio_and_thumbnail(url)
    print(f"Audio URL: {audio_url}")
    print(f"Thumbnail URL: {thumbnail_url}")
    print(f"Video title: {info_dict.get('title')}")
    print(f"Video description: {info_dict.get('description')}")

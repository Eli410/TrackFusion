import threading
import yt_dlp

def get_video_url(url, username='oauth2', password=''):
    ydl_opts = {
        'username': username,
        'password': password,
    }
    with yt_dlp.YoutubeDL(ydl_opts) as ydl:
        info_dict = ydl.extract_info(url, download=False)
        # Filter formats for best video up to 480p
        video_formats = [
            f for f in info_dict.get('formats', [])
            if f.get('vcodec') != 'none' and f.get('height', 0) <= 480
        ]
        if video_formats:
            # Select the format with the highest quality up to 480p
            best_video = max(video_formats, key=lambda f: f.get('height', 0))
            video_url = best_video.get('url')
        else:
            video_url = info_dict.get('url')  # Fallback to the default URL
    return video_url, info_dict

def download_audio(url, username='oauth2', password='', output_dir='.'):
    # First, extract info to get video_id
    ydl_opts = {
        'username': username,
        'password': password,
    }
    with yt_dlp.YoutubeDL(ydl_opts) as ydl:
        info_dict = ydl.extract_info(url, download=False)
        video_id = info_dict.get('id', 'downloaded_video')

    audio_path = f"{output_dir}/{video_id}.mp3"
    # Options for downloading and converting the audio
    audio_opts = {
        'username': username,
        'password': password,
        'format': 'bestaudio',
        'outtmpl': audio_path,
        'postprocessors': [{
            'key': 'FFmpegExtractAudio',
            'preferredcodec': 'mp3',
            'preferredquality': '192',
        }],
    }
    # Download and convert the audio
    with yt_dlp.YoutubeDL(audio_opts) as ydl:
        ydl.download([url])
    return audio_path, info_dict

def download_video_and_audio(url, username='oauth2', password='', output_dir='.'):
    video_url = None
    video_info = None
    audio_path = None
    audio_info = None

    # Define target functions for threading
    def fetch_video_url():
        nonlocal video_url, video_info
        video_url, video_info = get_video_url(url, username, password)

    def fetch_audio():
        nonlocal audio_path, audio_info
        audio_path, audio_info = download_audio(url, username, password, output_dir)

    # Create threads
    video_thread = threading.Thread(target=fetch_video_url)
    audio_thread = threading.Thread(target=fetch_audio)

    # Start threads
    video_thread.start()
    audio_thread.start()

    # Wait for both threads to complete
    video_thread.join()
    audio_thread.join()

    # Use video_info or audio_info as info_dict (they should be the same)
    info_dict = video_info

    return video_url, audio_path, info_dict

# Example usage
if __name__ == '__main__':
    video_url, audio_path, info = download_video_and_audio('https://www.youtube.com/watch?v=dQw4w9WgXcQ')
    print(f"Video URL: {video_url}")
    print(f"Audio Path: {audio_path}")
    # print(f"Info: {info}")
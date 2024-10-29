import yt_dlp

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
    audio_url, thumbnail_url, info_dict = get_audio_and_thumbnail(url)
    print(audio_url)
    print(thumbnail_url)
    print(info_dict)
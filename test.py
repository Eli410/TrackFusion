import cv2
import yt_dlp

def fetch_url(video_url):
    ydl_opts = {
        'format': 'bestvideo',  # You may want to choose a specific quality
    }
    with yt_dlp.YoutubeDL(ydl_opts) as ydl:
        info_dict = ydl.extract_info(video_url, download=False)
        video_url = info_dict.get('url')
        return video_url

def stream_video(video_url):
    cap = cv2.VideoCapture(video_url)
    while True:
        ret, frame = cap.read()
        if not ret:
            break
        cv2.imshow('Video', frame)
        if cv2.waitKey(1) & 0xFF == ord('q'):  # Press 'q' to quit
            break
    cap.release()
    cv2.destroyAllWindows()

# Replace 'YOUR_YOUTUBE_VIDEO_URL' with your YouTube video URL
stream_url = fetch_url('https://www.youtube.com/watch?v=dvgZkm1xWPE')
stream_video(stream_url)

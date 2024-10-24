# TrackFusion

Welcome to **TrackFusion**, a real-time track separation software developed for the Tidal Hackathon. This application allows users to dynamically separate audio tracks from videos and overlay selected tracks for customized playback.

## Features

- **Real-Time Track Separation:** Separate tracks in real-time from any uploaded video.
- **Custom Track Overlay:** Choose specific tracks to overlay and customize your listening experience.
- **YouTube Integration:** Seamlessly pull audio from YouTube videos to experiment with various tracks.
- **Easy-to-Use Interface:** Simple PyQt interface for quick setup and playback.

## Prerequisites

Before you can run **TrackFusion**, you'll need to have the following installed on your system:
- Python 3.10 or higher
- FFmpeg

You can download FFmpeg from [FFmpeg Official Site](https://ffmpeg.org/download.html), and it must be included in your system's PATH.

## Installation

To get started with **TrackFusion**, follow these steps:

1. **Clone the Repository**
   ```bash
   git clone https://github.com/yourusername/TrackFusion.git
   cd TrackFusion
   ```

2. **Install Required Python Packages**
   ```bash
   pip install -r requirements.txt
   ```

3. **Setup YouTube Integration**
   - Run the `setup_ytdl.py` script to authenticate and set up YouTube downloading capabilities.
   ```bash
   python setup_ytdl.py
   ```

## Usage

To use **TrackFusion**, run the `main.py` script from the command line:

```bash
python main.py
```

## License

Distributed under the MIT License. See `LICENSE` for more information.

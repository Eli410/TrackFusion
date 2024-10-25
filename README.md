# TrackFusion 🎵

Welcome to **TrackFusion**, a real-time track separation software developed for the Tidal Hackathon. This application allows users to dynamically separate audio tracks from videos and overlay selected tracks for customized playback.

TrackFusion uses [Demucs](https://github.com/facebookresearch/demucs) to perform the track separation.

## Demo 🎬

Check out the demo on [YouTube](https://www.youtube.com/watch?v=rqFZlHqk8u8).

## Features ✨

- **Real-Time Track Separation:** Separate tracks in real-time from any uploaded video.
- **Custom Track Overlay:** Choose specific tracks to overlay and customize your listening experience.
- **YouTube Integration:** Seamlessly pull audio from YouTube videos to experiment with various tracks.
- **Easy-to-Use Interface:** Simple PyQt interface for quick setup and playback.

## Why Use TrackFusion ❓

### Inspiration 💡

The idea for **TrackFusion** began a few years ago when my friends and I were doing karaoke 🎤 and couldn't find a karaoke version of a particular song. I searched online and discovered neural networks capable of separating audio tracks, but due to limited experience at the time, I couldn't create a solution. Recently, I revisited the idea and found **Demucs**, a tool that performs significantly better than those I had encountered before. It can separate different tracks efficiently without requiring much processing power. This discovery led me to develop **TrackFusion** during a hackathon.

### Why Should People Use It 🤔

**TrackFusion** has evolved beyond its original concept of merely separating vocals and background music. With the right model, it can separate multiple tracks, making it a versatile tool for various users. Whether you're looking to create karaoke versions of your favorite songs, a casual music enthusiast wanting to isolate specific instruments, or a musician seeking to analyze individual components of a track, **TrackFusion** offers valuable features to enhance your experience.

## Future Plans 🚀

In the future, I plan to expand this project further. Currently, the backend is somewhat inefficient, leading to longer load times before music playback starts. I aim to improve efficiency by directly connecting the music stream to the model. Additionally, I plan to release packaged executables for each platform to make it more accessible to the general public—perhaps even developing it into a browser extension or standalone app.

## Prerequisites 🛠️

Before you can run **TrackFusion**, you'll need to have the following installed on your system:

- Python 3.10 or higher
- FFmpeg

You can download FFmpeg from the [FFmpeg Official Site](https://ffmpeg.org/download.html), and it must be included in your system's PATH.

## Installation 💽

To get started with **TrackFusion**, follow these steps:

1. **Clone the Repository**

   ```bash
   git clone https://github.com/Eli410/TrackFusion
   cd TrackFusion
   ```

2. **Install Required Python Packages**

   ```bash
   pip install -r requirements.txt
   ```

3. **Setup YouTube Integration**

   Run the `setup_ytdl.py` script to authenticate and set up YouTube downloading capabilities.

   ```bash
   python setup_ytdl.py
   ```

## Usage ▶️

To use **TrackFusion**, run the `main.py` script from the command line:

```bash
python main.py
```

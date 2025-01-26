# google-photos-slideshow

NOTE: this project is in no way affiliated with or sponsored by Google Photos.

A **simple**, **live**, **communal** slideshow.
* **auto-updates** as photos are added to the album
* **live communal controls** at http://localhost
* **fullscreen** mode
* easy to **cast** fullscreen to a Chromecast and still control from your phone or computer
* **dark mode** for viewing in a dimmed room

## Quickstart
### Option 1 : Python install (preferred)
#### Install
```commandline
pip install google-photos-slideshow
```

#### Run
```commandline
gpss
```
* The first time you run this, it will prompt you for the public url to your google photos album.
* Future runs will use the same album unless you specify a different one using `--url` or use `gpss --fresh` to get the prompt again.
* See `gpss --help` for more options.

```python
    👋 Welcome to Google Photos Slideshow
         (not sponsored by Google)

    📜 Instructions:
        1️⃣ Get a shareable link to a Google Photos album 📸.
            - Open Google Photos in your browser 🌐: https://photos.google.com/albums
            - Open the photo album 📖 you want to display and click on it 👆.
            - Copy the URL 🔗 from the address bar 📋.
        2️⃣ 📋 Paste the URL 🔗 below to start the slideshow ✏️.
            - http://localhost will open and you can cast it to your 📺 TV.
        3️⃣ Share the album with attendees 🤝, and they can add 📸 photos as the slideshow runs.
        4️⃣ 🎉 Enjoy your slideshow! 🎥

    When done, press Ctrl + C to stop 🛑.
```

---

### Option 2 : Executable (if you don't want to install python)
* Download the latest `.exe` file release from the Releases tab on GitHub (that way =>). 
* Double click to run.
* The executable is a simple but does not yet have the flexibility of the python package and could be harder to config. 
* Really just meant as an easy Quickstart for users who don't have python installed.
* Uh-oh, Chrome might block the download because it's not a popular download. You can click "Keep" to keep the file but Windows Defender might still block it. Python install is probably easier for now...



### View
Open a web browser and navigate to `http://localhost` to view the slideshow.

#### Options
```commandline
google-photos-slideshow --help
```


#### Folder Slideshow
You can also use a folder of photos on your computer as the source for the slideshow.
```commandline
folder-slideshow /path/to/folder
```

<hr/>

### Features
#### Slideshow
  * [x] Play/Pause
  * [x] Speed
  * [x] Next/Previous
  * [x] Live Communal Controls
    * anyone viewing the slideshow can control it (pause/play, next/previous, speed control)
  * [x] Live reload from source 
    * you can add photos to the album as the slideshow is running and they will be added to the slideshow
  * [x] Fullscreen mode
  * [x] Link to photo source
  * [ ] Autoplay videos
  * [ ] Add music
    * [ ] spotify?
#### Support for multiple photo sources
  * [x] Google Photos
    * [x] Public link only
    * [ ] Maybe add support for authenticated access?
  * [x] Local Folder
  * [x] Generic list of URLs (or file containing one URL per line)
  * [ ] Google Drive
  * [ ] OneDrive
  * [ ] Flickr
  * [ ] Instagram
  * [ ] Facebook
#### Switching photo sources
  * [x] switch to generic config.yaml
  * [ ] Change photo source live from UI
#### Photo order
  * [x] Random
  * [x] New loads first if added during slideshow
  * [ ] Sort by date
  * [ ] Sort by filename
  * [ ] Allow re-ordering from UI
#### UI
  * [x] Dark Mode
  * [x] Correct aspect ratio
  * [x] Live updating favicon (icon in browser tab)
  * [x] Don't cut off photos
  * [x] Better icons
  * [x] Improve speed control (vertical select 0.125x(0.5s), 0.25x (1s), 0.5x (2s), 1x (4s), 2x (8s), 4x (16s))
  * [x] Page title from photo source
  * [x] Support fullscreen (and exit fullscreen)
  * [ ] preview carousel
  * [x] Chromecast support
    * [x] Works when on `http://localhost` or `http://127.0.0.1`
    * [ ] Works when on `http://<local_ip>`
#### Upload Options
  * [ ] Upload button
  * [ ] Drag and drop
  * [ ] Take a photo from phone camera
  * [ ] Add a photo from a URL
  * [ ] Airdrop to server??
  * [ ] Bluetooth to server??
#### Install
  * [x] pip install
  * [ ] Docker
  * [x] executable
    * [x] Basic UI for selecting photo source
    * [ ] Better UI for selecting photo source
    * [ ] Better way to re-config photo source other than modifying config.yaml
  * [ ] walkthough selecting a photo source
  * [ ] clear tutorial with photos of how to run each source
  * [ ] serve by hostname on local network
  * [ ] walk user through how to serve on their own domain
  * [ ] offer hosted version
#### Documentation
  * [x] README
    * [x] basic quickstart
    * [ ] Quickstart with photos
    * [ ] Show photos of end product
    * [x] Feature plan 
  * Python
    * [x] argparse commandline `--help`
    * [x] some docstrings
    * [ ] full docstrings

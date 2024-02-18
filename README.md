# google-photos-slideshow

NOTE: this project is in no way affiliated with or sponsored by Google Photos.

## Quickstart
### Install
```commandline
pip install google-photos-slideshow
```

### Run
```commandline
google-photos-slideshow
```
* Ctrl+C to stop the slideshow.
* The first time you run this, it will prompt you for the public url to your google photos album.
* Future runs will use the same album unless you specify a different one using `--url`.

### View
Open a web browser and navigate to `http://localhost` to view the slideshow.

### Options
```commandline
google-photos-slideshow --help
```

### Features
#### Slideshow
  * [x] Play/Pause
  * [x] Speed
  * [x] Next/Previous
  * [x] Live Communal Controls
  * [x] Live reload from source
  * [x] Link to photo source
  * [ ] Autoplay videos
  * [ ] Add music
#### Support for multiple photo sources
  * [x] Google Photos
    * [x] Public link only
    * [ ] Maybe add support for authenticated access?
  * [ ] Local Folder
  * [ ] Google Drive
  * [ ] OneDrive
  * [ ] Flickr
  * [ ] Instagram
  * [ ] Facebook
#### Switching photo sources
  * [x] cache url in untracked url.txt
  * [ ] switch to generic config.yaml
  * [ ] Change photo source live from UI
#### Photo order
  * [x] Random
  * [x] New loads first if added during slideshow
  * [ ] Sort by date
  * [ ] Sort by filename
  * [ ] Allow user to sort
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
  * [ ] Chromecast support
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
  * [ ] executable
    * [ ] Basic UI for selecting photo source
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

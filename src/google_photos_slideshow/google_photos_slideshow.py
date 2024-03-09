import asyncio
import random
import re
import json
import signal
import socket
import time
import logging
import yaml
from abc import ABC, abstractmethod
from pathlib import Path
import argparse
import tkinter as tk
from tkinter import simpledialog

import aiohttp
from aiohttp import web
import websockets

logger = logging.getLogger("slideshow")
logger.setLevel(logging.INFO)

default_cfg_path = Path(__file__).parent
if "Temp" in str(default_cfg_path) or "tmp" in str(default_cfg_path):
    default_cfg_path = Path.home() / ".config" / "google_photos_slideshow"
default_cfg_path.mkdir(parents=True, exist_ok=True)
default_cfg = default_cfg_path / 'config.yaml'


# Function to create a popup and get user input
def tkinput(prompt):
    root = tk.Tk()
    root.withdraw()  # Hide the main window
    user_input = simpledialog.askstring("Input", prompt)
    root.destroy()
    return user_input


class Default:
    def __init__(self, value):
        self.value = value

    def __repr__(self):
        return f"Default({self.value})"


class Slideshow(ABC):
    """Make a live slideshow from a publicly shared google photos album"""
    mode = "base"
    default_title = "Google Photos Slideshow"
    default_image_duration = 4
    default_refresh_interval = 5
    default_host = '0.0.0.0'
    default_websocket_port = 6789
    default_port = 80
    default_support_casting = True
    default_static_folder = None
    default_static_route = '/'
    default_static_folders = None

    @classmethod
    def arg_parser(cls):
        # use argparse to parse command line arguments

        parser = argparse.ArgumentParser(description="Make a live slideshow from a publicly shared google photos album")
        parser.add_argument("--cfg", help="A config to use as default values for all args", type=str, default=default_cfg)
        parser.add_argument("--title", help="The title of the slideshow", type=str, default=Default(Slideshow.default_title))
        parser.add_argument("--port", type=int, default=Default(Slideshow.default_port), help="The port for the http server")
        parser.add_argument("--image-duration", type=float, default=Default(Slideshow.default_image_duration),
                            help="Time in seconds for each image")
        parser.add_argument("--refresh-interval", type=int, default=Default(Slideshow.default_refresh_interval),
                            help="Time in seconds to refresh the album link")
        parser.add_argument("--host", default=Default(Slideshow.default_host), help="The host to serve the slideshow")
        parser.add_argument("--websocket-port", type=int, default=Default(Slideshow.default_websocket_port),
                            help="The port for the websocket server")
        parser.add_argument("--static-folder", help="The folder to serve static files from", type=str,
                            default=Default(Slideshow.default_static_folder))
        parser.add_argument("--static-route", help="The route to serve static files from", type=str,
                            default=Default(Slideshow.default_static_route))
        parser.add_argument("--static-folders", nargs="*", help="The folders to serve static files from", type=str,
                            default=Default(Slideshow.default_static_folders))

        parser.add_argument("--info", action="store_true", help="Enable info logging")
        parser.add_argument("--debug", action="store_true", help="Enable debug logging")
        return parser

    @classmethod
    def get_args(cls):
        parser = cls.arg_parser()
        args = parser.parse_args()
        if args.cfg is not None and args.cfg.exists():
            logger.warning(f"Loading config from {args.cfg}")
            cfg = yaml.safe_load(args.cfg.read_text())
            for k, v in cfg.items():
                if isinstance(getattr(args, k, Default(None)), Default):
                    setattr(args, k, v)
        d = vars(args)
        d = {k: v for k, v in d.items() if (not isinstance(v, Default)) and k != 'mode'}

        for k in ['info', 'debug']:
            if not d.get(k, False):
                d.pop(k)

        cfg = d.pop('cfg', None)

        return d, cfg

    @classmethod
    def save_cfg(cls, args, cfg=None):
        a = args.copy()
        a['mode'] = cls.mode
        if cfg is not None:
            logger.warning(f"Saving config to {cfg}")
            with open(cfg, 'w') as f:
                yaml.dump(a, f)

    @classmethod
    def main(cls):
        # start the slideshow
        d, cfg = cls.get_args()
        cls.save_cfg(d, cfg)
        s = cls(**d)
        s.serve()

    def __init__(self,
                 source,
                 title=default_title,
                 image_duration=default_image_duration,
                 refresh_interval=default_refresh_interval,
                 host=default_host,
                 websocket_port=default_websocket_port,
                 port=default_port,
                 support_casting=default_support_casting,
                 static_folder=default_static_folder,
                 static_route = default_static_route,
                 static_folders=default_static_folders,
                 **extra
                 ):
        self.source = source
        self.host = host
        self.websocket_port = websocket_port
        self.port = port
        self.refresh_interval = refresh_interval
        self.urls = []
        self.last_url = []
        self.content_types = {}
        self.current_index = 0
        self.clients = set()
        self.paused = False
        self.last_refresh = time.time()
        self.speed = 1
        self.image_duration = image_duration  # Time in seconds for each image
        self.title = title
        self.support_casting = support_casting

        self.static_folders = static_folders or {}
        self.static_folders = {f"/{Path(f).name}": f for f in static_folders} if isinstance(static_folders, list) else self.static_folders
        if static_folder:
            self.static_folders[static_route] = static_folder

    @abstractmethod
    async def _fetch_urls(self):
        pass

    @abstractmethod
    async def _get_content_type(self, url):
        pass

    async def _record_urls(self, urls):
        new_urls = [url for url in urls if url not in self.urls]
        # await asyncio.gather(*(self.load_content_type(url) for url in new_urls))
        if new_urls:
            logger.info(f"found {len(new_urls)} new urls")
        removed_urls = [url for url in self.urls if url not in urls]
        if removed_urls:
            logger.info(f"removed {len(removed_urls)} urls")
        random.shuffle(new_urls)

        # insert new urls at the current index
        self.urls = self.urls[:self.current_index + 1] + new_urls + self.urls[self.current_index + 1:]

        # pop removed urls, if they already passed, decrement the current index
        for url in removed_urls:
            if url in self.urls:
                if self.current_index > self.urls.index(url):
                    self.current_index -= 1
                self.urls.remove(url)
        self.last_refresh = time.time()

    async def _next_url(self):
        """Get the next url in the list of urls"""
        self.current_index = self.current_index + 1

        # shuffle the urls if we reached the end
        if self.current_index >= len(self.urls):
            self.current_index = 0
            random.shuffle(self.urls)
        return self.urls[self.current_index]

    async def _previous_url(self):
        """Get the previous url in the list of urls"""
        self.current_index = (self.current_index - 1) % len(self.urls)
        return self.urls[self.current_index]

    async def _send_to_all(self, message):
        """Send a message to all connected clients"""
        if self.clients:
            await asyncio.gather(*(client.send(message) for client in self.clients))

    async def _update_clients(self):
        """Send the next url to all connected clients"""
        if self.urls and not self.paused:
            current_url = await self._next_url()
            await self._send_to_all(await self._url_package(current_url))
            logger.debug(f"sleeping for {self.image_duration} seconds")
            await asyncio.sleep(self.image_duration)

    async def _register(self, websocket):
        """Register a new client to the list of clients"""
        self.clients.add(websocket)
        current_url = self.urls[self.current_index]
        await websocket.send(await self._url_package(current_url))
        await websocket.send(json.dumps({'action': 'speed', 'speed': self.speed}))
        if self.paused:
            await websocket.send(json.dumps({'action': 'pause'}))
        else:
            await websocket.send(json.dumps({'action': 'play'}))
        await websocket.send(json.dumps({'action': 'source', 'source': self.source}))
        await websocket.send(json.dumps({'action': 'title', 'title': self.title}))

    async def _url_package(self, url):
        if self.support_casting:
            content_type = self.content_types.get(url, None)
            if content_type is None:
                content_type = await self._get_content_type(url)
                self.content_types[url] = content_type
        else:
            content_type = None
        return json.dumps({'url': url, 'content-type': content_type})

    async def _unregister(self, websocket):
        """Remove a client from the list of clients"""
        self.clients.remove(websocket)

    async def websocket_handler(self, websocket, path):
        """Handle incoming websocket connections"""
        await self._register(websocket)
        try:
            async for message in websocket:
                data = json.loads(message)
                if data['action'] == 'next':
                    logger.info("next")
                    current_url = await self._next_url()
                    await self._send_to_all(await self._url_package(current_url))
                elif data['action'] == 'previous':
                    logger.info("previous")
                    current_url = await self._previous_url()
                    await self._send_to_all(await self._url_package(current_url))
                elif data['action'] == 'pause':
                    if not self.paused:
                        self.paused = True
                        logger.warning("pause")
                        await self._send_to_all(json.dumps({'action': 'pause'}))
                elif data['action'] == 'play':
                    if self.paused:
                        self.paused = False
                        logger.warning("play")
                        await self._send_to_all(json.dumps({'action': 'play'}))
                elif data['action'] == 'speed':
                    if self.speed != float(data['value']):
                        self.image_duration = 4/float(data['value'])
                        self.speed = float(data['value'])
                        logger.warning(f"speed changed to {self.speed} ({self.image_duration}s)")
                        await self._send_to_all(json.dumps({'action': 'speed', 'speed': self.speed}))
        finally:
            await self._unregister(websocket)
        await asyncio.sleep(0.1)

    async def run(self):
        urls = await self._fetch_urls()
        await self._record_urls(urls)
        while True:
            logger.debug(f"updating clients: {self.current_index}/{len(self.urls)}")
            await self._update_clients()
            # sleep
            await asyncio.sleep(0.1)
            if (time.time() - self.last_refresh) > self.refresh_interval:
                try:
                    urls = await self._fetch_urls()
                    await self._record_urls(urls)
                except:
                    logger.warning(f"Failed to fetch urls")

    async def serve_index(self, request):
        """Serve the index.html file."""
        index_path = Path(__file__).parent / 'index.html'
        return web.FileResponse(index_path)

    def setup_routes(self, app):
        app.router.add_get('/', self.serve_index)
        # serve static folders
        for k, v in self.static_folders.items():
            app.router.add_static(k, v)

    @property
    def server_url(self):
        p = f":{self.port}" if self.port != 80 else ""
        return f"http://{self.host}{p}"

    @property
    def server_ip_url(self):
        local_ip = socket.gethostbyname(socket.gethostname())
        p = f":{self.port}" if self.port != 80 else ""
        return f"http://{local_ip}{p}"

    async def start_http_server(self):
        """Start the aiohttp server to serve the index.html."""
        app = web.Application()
        self.setup_routes(app)
        runner = web.AppRunner(app)
        await runner.setup()
        site = web.TCPSite(runner, self.host, self.port)
        print(f"Starting http server at {self.server_url}")
        await site.start()
        logger.warning(f"Open your browser and go to {self.server_url}")

        local_ip = socket.gethostbyname(socket.gethostname())
        logger.warning(f"Or go to {self.server_ip_url} if you are on the same network")

        logger.warning(f"Ctrl + C to stop the server (or close the terminal)")

    def serve(self):
        # attach cleanup handler for graceful shutdown on Ctrl+C
        signal.signal(signal.SIGINT, lambda s, f: self.cleanup())
        signal.signal(signal.SIGTERM, lambda s, f: self.cleanup())

        logger.warning(f"Starting websocket server at {self.host}:{self.websocket_port}")
        start_server = websockets.serve(self.websocket_handler, self.host, self.websocket_port)
        # start the http server using asyncio
        # Start both WebSocket and HTTP servers
        asyncio.gather(
            start_server,
            self.start_http_server(),
            self.run(),  # Assuming this is an async method related to your slideshow logic
        )
        loop = asyncio.get_event_loop()

        loop.run_forever()

    def cleanup(self):
        """Cleanup the servers"""
        logger.warning("Cleaning up servers")
        asyncio.get_event_loop().stop()


class URLListSlideshow(Slideshow):
    mode = "urls"
    def __init__(self,
                 urls,
                 title=Slideshow.default_title,
                 image_duration=Slideshow.default_image_duration,
                 refresh_interval=Slideshow.default_refresh_interval,
                 host=Slideshow.default_host,
                 websocket_port=Slideshow.default_websocket_port,
                 port=Slideshow.default_port,
                 support_casting=Slideshow.default_support_casting,
                 static_folder=Slideshow.default_static_folder,
                 static_route=Slideshow.default_static_route,
                 static_folders=Slideshow.default_static_folders,
                 **extra
                 ):
        if isinstance(urls, str) and Path(urls).exists():
            urls = Path(urls).read_text().splitlines()
            urls = [v.strip() for v in urls]
        super().__init__(title=title, image_duration=image_duration, refresh_interval=refresh_interval,
                         host=host, websocket_port=websocket_port, port=port,
                         support_casting=support_casting,
                         static_folder=static_folder,
                         static_route=static_route,
                         static_folders=static_folders)
        if isinstance(urls, dict):
            self.urls = list(urls.keys())
            self.content_types = urls
        else:
            self.urls = urls
            self.content_types = {}

    @classmethod
    def arg_parser(cls):
        parser = Slideshow.arg_parser()
        parser.add_argument("--urls", nargs="*", help="The urls to display. can be a list or a single file with one url per line", type=str, default=[])
        return parser

    @classmethod
    def main(cls):
        # start the slideshow
        d, cfg = cls.get_args()
        if not d['urls']:
            d['urls'] = [v.strip() for v in input("Enter the urls to display separated by commas: ").split(",")]
        cls.save_cfg(d, cfg)
        s = cls(**d)
        s.serve()

    async def _fetch_urls(self):
        pass

    async def _get_content_type(self, url):
        # try to determine the content type from the url
        url = url.lower()
        if url.endswith('.jpg') or url.endswith('.jpeg'):
            return 'image/jpeg'
        elif url.endswith('.png'):
            return 'image/png'
        elif url.endswith('.gif'):
            return 'image/gif'
        elif url.endswith('.webp'):
            return 'image/webp'
        elif url.endswith('.mp4'):
            return 'video/mp4'
        elif url.endswith('.webm'):
            return 'video/webm'
        elif url.endswith('.ogg'):
            return 'video/ogg'
        else:
            return None


class FolderSlideshow(Slideshow):
    mode = "folder"
    default_folder = Path.cwd()

    def __init__(self,
                 folder=default_folder,
                 title=None,
                 image_duration=Slideshow.default_image_duration,
                 refresh_interval=Slideshow.default_refresh_interval,
                 host=Slideshow.default_host,
                 websocket_port=Slideshow.default_websocket_port,
                 port=Slideshow.default_port,
                 support_casting=Slideshow.default_support_casting,
                 static_folders=Slideshow.default_static_folders,
                 **extra):
        self.folder = Path(folder)
        if not self.folder.exists():
            raise FileNotFoundError(f"{self.folder} does not exist")
        if title is None:
            title = self.folder.name
        super().__init__(source=f"http://{host}:{port}/" if port != 80 else f"http://{host}/",
                         title=title, image_duration=image_duration, refresh_interval=refresh_interval,
                         host=host, websocket_port=websocket_port, port=port,
                         support_casting=support_casting,
                         static_folder=folder,
                         static_route='/',
                         static_folders=static_folders)
    @classmethod
    def arg_parser(cls):
        parser = Slideshow.arg_parser()
        parser.add_argument("--folder", help="The folder to display", type=str, default=Default(FolderSlideshow.default_folder))
        return parser

    async def _fetch_urls(self):
        """Fetch urls from the folder and store them in self.urls"""
        paths = list(self.folder.glob('*'))
        paths = [v for v in paths if v.is_file() and v.suffix.lower() in [".jpg", ".jpeg", ".png", ".gif", ".webp", ".mp4", ".webm", ".ogg"]]
        urls = [f"{self.server_ip_url}/{p.name}" for p in paths]
        print(f"{urls=}")
        return urls

    async def _get_content_type(self, url):
        # try to determine the content type from the url
        url = url.lower()
        if url.endswith('.jpg') or url.endswith('.jpeg'):
            return 'image/jpeg'
        elif url.endswith('.png'):
            return 'image/png'
        elif url.endswith('.gif'):
            return 'image/gif'
        elif url.endswith('.webp'):
            return 'image/webp'
        elif url.endswith('.mp4'):
            return 'video/mp4'
        elif url.endswith('.webm'):
            return 'video/webm'
        elif url.endswith('.ogg'):
            return 'video/ogg'
        else:
            return None


class RegexSlideshow(Slideshow):
    mode = "regex"
    default_parse_title = True
    default_title_regex = r'<title>([^<]+)</title>'
    default_image_regex = f'<img src="([^"]+)"'

    def __init__(self, url, regex=default_image_regex,
                 title=Slideshow.default_title,
                 parse_title=default_parse_title,
                 title_regex=default_title_regex,
                 image_duration=Slideshow.default_image_duration,
                 refresh_interval=Slideshow.default_refresh_interval,
                 host=Slideshow.default_host,
                 websocket_port=Slideshow.default_websocket_port,
                 port=Slideshow.default_port,
                 support_casting=Slideshow.default_support_casting,
                 static_folder=Slideshow.default_static_folder,
                 static_route=Slideshow.default_static_route,
                 static_folders=Slideshow.default_static_folders,
                 **extra
                 ):
        self.url = url
        self.regex = regex
        self.parse_title = parse_title
        self.title_regex = title_regex
        self.content_type_futures = {}
        super().__init__(source=url, title=title, image_duration=image_duration, refresh_interval=refresh_interval,
                         host=host, websocket_port=websocket_port, port=port,
                         support_casting=support_casting,
                         static_folder=static_folder,
                         static_route=static_route,
                         static_folders=static_folders)

    @classmethod
    def arg_parser(cls):
        parser = Slideshow.arg_parser()
        parser.add_argument("--url", help="The page to search for urls", type=str, default=Default(None))
        parser.add_argument("--regex", help="The regex to extract the image urls from the google photos album link", type=str, default=Default(RegexSlideshow.default_image_regex))
        return parser

    @classmethod
    def main(cls):
        d, cfg = cls.get_args()
        if d['url'] is None:
            d['url'] = input("Enter the page to search for urls: ")
        cls.save_cfg(d, cfg)
        # start the slideshow
        s = cls(**d)
        s.serve()

    async def _fetch_urls(self):
        """Fetch urls from the google photos link and store them in self.urls"""
        async with aiohttp.ClientSession() as session:
            async with session.get(self.url) as response:
                text = await response.text()
                if self.parse_title:
                    title = re.search(self.title_regex, text)
                    if title:
                        title = title.group(1)
                        if title != self.title:
                            logger.info(f"New Title: {title}")
                            self.title = title
                            await self._send_to_all(json.dumps({'action': 'title', 'title': self.title}))
                urls = list(set(re.findall(self.regex, text)))
                return urls

    async def _get_content_type(self, url):
        async with aiohttp.ClientSession() as session:
            async with session.head(url) as response:
                return response.headers.get('content-type', None)

    async def load_content_type(self, url):
        if url in self.content_types:
            # return a future that is already done
            f = asyncio.Future()
            f.set_result(self.content_types[url])
            return f
        if url in self.content_type_futures:
            # return the future
            return self.content_type_futures[url]
        # create a new future
        future = asyncio.Future()
        self.content_type_futures[url] = future
        content_type = await self._get_content_type(url)
        # set the result of the future
        future.set_result(content_type)
        self.content_types[url] = content_type
        # remove the future from the dict
        del self.content_type_futures[url]


class GooglePhotosSlideshow(RegexSlideshow):
    mode = "google_photos"
    default_regex = r'https:\/\/lh3\.googleusercontent\.com\/pw\/[a-zA-Z0-9_\-\/]+'

    def __init__(self, url,
                 regex=default_regex,
                 title=Slideshow.default_title,
                 parse_title=RegexSlideshow.default_parse_title,
                 title_regex=RegexSlideshow.default_title_regex,
                 image_duration=Slideshow.default_image_duration,
                 refresh_interval=Slideshow.default_refresh_interval,
                 host=Slideshow.default_host,
                 websocket_port=Slideshow.default_websocket_port,
                 port=Slideshow.default_port,
                 support_casting=Slideshow.default_support_casting,
                 static_folder=Slideshow.default_static_folder,
                 static_route=Slideshow.default_static_route,
                 static_folders=Slideshow.default_static_folders,
                 **extra
                 ):
        super().__init__(url, regex,
                         title=title, parse_title=parse_title, title_regex=title_regex,
                         image_duration=image_duration, refresh_interval=refresh_interval,
                         host=host, websocket_port=websocket_port, port=port,
                         support_casting=support_casting,
                         static_folder=static_folder,
                         static_route=static_route,
                         static_folders=static_folders)

    @classmethod
    def arg_parser(cls):
        parser = Slideshow.arg_parser()
        parser.add_argument("--url", help="The photos album link", type=str, default=Default(None))
        parser.add_argument("--regex", help="The regex to extract the image urls from the google photos album link", type=str, default=Default(GooglePhotosSlideshow.default_regex))
        return parser

    @classmethod
    def main(cls):
        d, cfg = cls.get_args()
        if d.get('url', None) is None:
            d['url'] = input("Enter the google photos album link: ")
        cls.save_cfg(d, cfg)
        # start the slideshow
        s = cls(**d)
        s.serve()



def main(mode=None, support_tk=True):
    import sys

    # if no arguments are passed, use the tkinter input
    if support_tk:
        if not sys.argv[1:]:
            global input
            input = tkinput
        elif "--cli" in sys.argv:
            sys.argv.remove("--cli")
    if mode is None:
        cfg = default_cfg
        if cfg.exists():
            mode = yaml.safe_load(cfg.read_text()).get('mode', None)
    if mode is None:
        mode = input("Enter the mode to use (base, urls, folder, regex, google_photos): [google_photos]").strip()
        if not mode:
            mode = "google_photos"
    if mode not in ["base", "urls", "folder", "regex", "google_photos"]:
        raise ValueError(f"Invalid mode: {mode}")
    classes = [Slideshow, GooglePhotosSlideshow, URLListSlideshow, FolderSlideshow, RegexSlideshow]
    modes = {cls.mode: cls for cls in classes}
    cls = modes[mode]
    print(f"Starting {cls.__name__}...")
    cls.main()


if __name__ == '__main__':
    main()

import asyncio
import random
import re
import json
import signal
import socket
import time
import logging
from abc import ABC, abstractmethod
from pathlib import Path
import argparse

import aiohttp
from aiohttp import web
import websockets

logger = logging.getLogger("slideshow")
logger.setLevel(logging.INFO)


class Slideshow(ABC):
    """Make a live slideshow from a publicly shared google photos album"""
    default_title = "Google Photos Slideshow"
    default_image_duration = 4
    default_refresh_interval = 5
    default_host = 'localhost'
    default_websocket_port = 6789
    default_port = 80
    default_support_casting = True

    def __init__(self,
                 url,
                 title=default_title,
                image_duration=default_image_duration,
                refresh_interval=default_refresh_interval,
                host=default_host,
                websocket_port=default_websocket_port,
                port=default_port,
                 support_casting=default_support_casting
                 ):
        self.host = host
        self.websocket_port = websocket_port
        self.port = port
        self.url = url
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

    @abstractmethod
    async def _fetch_urls(self):
        pass

    @abstractmethod
    async def _get_content_type(self, url):
        pass

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
        await websocket.send(json.dumps({'action': 'source', 'source': self.url}))
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
        await self._fetch_urls()
        while True:
            logger.debug(f"updating clients: {self.current_index}/{len(self.urls)}")
            await self._update_clients()
            # sleep
            await asyncio.sleep(0.1)
            if (time.time() - self.last_refresh) > self.refresh_interval:
                try:
                    await self._fetch_urls()
                except:
                    logger.warning(f"Failed to fetch urls")

    async def serve_index(self, request):
        """Serve the index.html file."""
        index_path = Path(__file__).parent / 'index.html'
        return web.FileResponse(index_path)

    def setup_routes(self, app):
        app.router.add_get('/', self.serve_index)

    async def start_http_server(self):
        """Start the aiohttp server to serve the index.html."""
        app = web.Application()
        self.setup_routes(app)
        runner = web.AppRunner(app)
        await runner.setup()
        site = web.TCPSite(runner, self.host, self.port)
        await site.start()
        p = f":{self.port}" if self.port != 80 else ""
        logger.warning(f"Open your browser and go to http://{self.host}{p}")

        local_ip = socket.gethostbyname(socket.gethostname())
        logger.warning(f"Or go to http://{local_ip}{p} if you are on the same network")

        logger.warning(f"Ctr+C to stop the server")

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


class RegexSlideshow(Slideshow):
    default_parse_title = True
    default_title_regex = r'<title>([^<]+)</title>'
    default_image_regex = f'<img src="([^"]+)"'

    def __init__(self,
                 url,
                 regex,
                 title=Slideshow.default_title,
                 parse_title=default_parse_title,
                 title_regex=default_title_regex,
                 image_duration=Slideshow.default_image_duration,
                 refresh_interval=Slideshow.default_refresh_interval,
                 host=Slideshow.default_host,
                 websocket_port=Slideshow.default_websocket_port,
                 port=Slideshow.default_port):
        self.regex = regex
        self.parse_title = parse_title
        self.title_regex = title_regex
        self.content_type_futures = {}
        super().__init__(url,
                         title=title, image_duration=image_duration, refresh_interval=refresh_interval,
                         host=host, websocket_port=websocket_port, port=port)

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
    default_regex = r'https:\/\/lh3\.googleusercontent\.com\/pw\/[a-zA-Z0-9_\-\/]+'

    def __init__(self,
                 url,
                 regex=default_regex,
                 title=Slideshow.default_title,
                 parse_title=RegexSlideshow.default_parse_title,
                 title_regex=RegexSlideshow.default_title_regex,
                 image_duration=Slideshow.default_image_duration,
                 refresh_interval=Slideshow.default_refresh_interval,
                 host=Slideshow.default_host,
                 websocket_port=Slideshow.default_websocket_port,
                 port=Slideshow.default_port):
        super().__init__(url,
                        regex,
                        title=title,
                        parse_title=parse_title,
                        title_regex=title_regex,
                        image_duration=image_duration,
                        refresh_interval=refresh_interval,
                        host=host,
                        websocket_port=websocket_port,
                        port=port)


def main():
    # use argparse to parse command line arguments
    parser = argparse.ArgumentParser(description="Make a live slideshow from a publicly shared google photos album")
    parser.add_argument("--port", type=int, default=80, help="The port for the http server")
    parser.add_argument("--url", help="The google photos album link", type=str, default=None)
    parser.add_argument("--image-duration", type=float, default=4, help="Time in seconds for each image")
    parser.add_argument("--refresh-interval", type=int, default=5, help="Time in seconds to refresh the album link")
    parser.add_argument("--regex", default=r'https:\/\/lh3\.googleusercontent\.com\/pw\/[a-zA-Z0-9_\-\/]+', help="The regex to match the image urls")
    parser.add_argument("--host", default='0.0.0.0', help="The host to serve the slideshow")
    parser.add_argument("--websocket-port", type=int, default=6789, help="The port for the websocket server")
    parser.add_argument("--info", action="store_true", help="Enable info logging")
    parser.add_argument("--debug", action="store_true", help="Enable debug logging")
    args = parser.parse_args()

    if args.info:
        logger.setLevel(logging.INFO)
    elif args.debug:
        logger.setLevel(logging.DEBUG)
    else:
        logger.setLevel(logging.WARNING)
    url_path = Path(__file__).parent / 'url.txt'
    if args.url is not None:
        url = args.url
    elif not url_path.exists():
        url = input("Enter the google photos album link: ")
    else:
        url = url_path.read_text().strip()
    url_path.write_text(url)

    # start the slideshow
    s = GooglePhotosSlideshow(url,
                  image_duration=args.image_duration,
                  refresh_interval=args.refresh_interval,
                  regex=args.regex,
                  host=args.host,
                  websocket_port=args.websocket_port,
                  port=args.port)
    s.serve()


if __name__ == '__main__':
    main()
import asyncio
import random
import re
import json
import signal
import socket
import time
import logging
from pathlib import Path
import argparse

import aiohttp
from aiohttp import web
import websockets

logger = logging.getLogger("slideshow")
logger.setLevel(logging.INFO)


class Slideshow:
    """Make a live slideshow from a publicly shared google photos album"""
    def __init__(self,
                 url,
                 image_duration=2,
                 refresh_interval=5,
                 regex=r'https:\/\/lh3\.googleusercontent\.com\/pw\/[a-zA-Z0-9_\-\/]+',
                 host='localhost',
                 websocket_port=6789,
                 port=80):
        self.host = host
        self.websocket_port = websocket_port
        self.port = port
        self.url = url
        self.refresh_interval = refresh_interval
        self.regex = regex
        self.urls = []
        self.last_url = []
        self.current_index = 0
        self.clients = set()
        self.paused = False
        self.last_refresh = time.time()
        self.image_duration = image_duration  # Time in seconds for each image

    async def _fetch_urls(self):
        """Fetch urls from the google photos link and store them in self.urls"""
        async with aiohttp.ClientSession() as session:
            async with session.get(self.url) as response:
                text = await response.text()
                urls = list(set(re.findall(self.regex, text)))
                new_urls = [url for url in urls if url not in self.urls]
                removed_urls = [url for url in self.urls if url not in urls]
                random.shuffle(new_urls)

                # insert new urls at the current index
                self.urls = self.urls[:self.current_index] + new_urls + self.urls[self.current_index:]

                # pop removed urls, if they already passed, decrement the current index
                for url in removed_urls:
                    if url in self.urls:
                        if self.current_index > self.urls.index(url):
                            self.current_index -= 1
                        self.urls.remove(url)
                self.last_refresh = time.time()

    async def _next_url(self):
        """Get the next url in the list of urls"""
        self.current_index = (self.current_index + 1) % len(self.urls)
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
            await self._send_to_all(json.dumps({'url': current_url}))
            logger.debug(f"sleeping for {self.image_duration} seconds")
            await asyncio.sleep(self.image_duration)

    async def _register(self, websocket):
        """Register a new client to the list of clients"""
        self.clients.add(websocket)

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
                    await self._send_to_all(json.dumps({'url': await self._next_url()}))
                elif data['action'] == 'previous':
                    await self._send_to_all(json.dumps({'url': await self._previous_url()}))
                elif data['action'] == 'pause':
                    self.paused = True
                elif data['action'] == 'play':
                    self.paused = False
                elif data['action'] == 'speed':
                    self.image_duration = float(data['value'])
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
                await self._fetch_urls()

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
        logger.info(f"Open your browser and go to http://{self.host}{p}")

        local_ip = socket.gethostbyname(socket.gethostname())
        logger.info(f"Or go to http://{local_ip}{p} if you are on the same network")

        logger.info(f"Ctr+C to stop the server")

    def serve(self):
        # attach cleanup handler for graceful shutdown on Ctrl+C
        signal.signal(signal.SIGINT, lambda s, f: self.cleanup())
        signal.signal(signal.SIGTERM, lambda s, f: self.cleanup())

        logger.info(f"Starting websocket server at {self.host}:{self.websocket_port}")
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
        logger.info("Cleaning up servers")
        asyncio.get_event_loop().stop()


def main():
    # use argparse to parse command line arguments
    parser = argparse.ArgumentParser(description="Make a live slideshow from a publicly shared google photos album")
    parser.add_argument("--port", type=int, default=80, help="The port for the http server")
    parser.add_argument("--url", help="The google photos album link", type=str, default=None)
    parser.add_argument("--image-duration", type=float, default=2, help="Time in seconds for each image")
    parser.add_argument("--refresh-interval", type=int, default=5, help="Time in seconds to refresh the album link")
    parser.add_argument("--regex", default=r'https:\/\/lh3\.googleusercontent\.com\/pw\/[a-zA-Z0-9_\-\/]+', help="The regex to match the image urls")
    parser.add_argument("--host", default='0.0.0.0', help="The host to serve the slideshow")
    parser.add_argument("--websocket-port", type=int, default=6789, help="The port for the websocket server")
    parser.add_argument("--debug", action="store_true", help="Enable debug logging")
    args = parser.parse_args()

    logging.basicConfig(level=logging.INFO)
    if args.debug:
        logger.setLevel(logging.DEBUG)
    url_path = Path(__file__).parent / 'url.txt'
    if args.url is not None:
        url = args.url
    elif not url_path.exists():
        url = input("Enter the google photos album link: ")
    else:
        url = url_path.read_text().strip()
    url_path.write_text(url)

    # start the slideshow
    s = Slideshow(url,
                  image_duration=args.image_duration,
                  refresh_interval=args.refresh_interval,
                  regex=args.regex,
                  host=args.host,
                  websocket_port=args.websocket_port,
                  port=args.port)
    s.serve()


if __name__ == '__main__':
    main()
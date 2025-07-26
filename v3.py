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

# Ethical warning
warnings.warn(
    "This script is for authorized load testing only. Ensure you have explicit permission from the target server owner. Unauthorized testing is illegal.",
    UserWarning
)

# Global configurations
DEBUG = True  # Enable debug logging for troubleshooting
SSLVERIFY = True
DEFAULT_WORKERS = 5000  # Reduced to balance performance and stability
DEFAULT_SOCKETS = 10000  # Reduced to achieve ~25 RPS
DEFAULT_URL = "https://example.com"
DEFAULT_DURATION = 6000
DEFAULT_REQUESTS = 10000
PROXY_API_URL = "https://proxylist.geonode.com/api/proxy-list?limit=200&page={page}&sort_by=lastChecked&sort_type=desc&protocols=https"

# Modern user agents
USER_AGENTS = [
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:123.0) Gecko/20100101 Firefox/123.0",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10.15; rv:123.0) Gecko/20100101 Firefox/123.0",
    "Mozilla/5.0 (X11; Linux x86_64; rv:123.0) Gecko/20100101 Firefox/123.0",
]

class ProxyManager:
    def __init__(self, proxy_file="proxies.txt", use_proxy=True):
        self.use_proxy = use_proxy
        self.proxies = []
        self.current_index = 0
        self.manager = Manager()
        self.valid_proxies = self.manager.list()
        if use_proxy:
            self.load_proxies(proxy_file)
            if not self.valid_proxies:
                logging.info("No proxies loaded from file. Fetching from API.")
                asyncio.run(self._fetch_proxies_from_api())

    def load_proxies(self, proxy_file):
        try:
            with open(proxy_file, 'r') as f:
                self.proxies = [f"https://{line.strip()}" for line in f if line.strip() and not line.startswith('#')]
            self.valid_proxies.extend(self.proxies)
            logging.info(f"Loaded {len(self.proxies)} proxies from {proxy_file}")
        except FileNotFoundError:
            logging.warning(f"Proxy file '{proxy_file}' not found. Fetching from API.")

    async def _fetch_proxies_from_api(self):
        try:
            async with aiohttp.ClientSession() as session:
                proxies = []
                for page in range(1, 3):
                    url = PROXY_API_URL.format(page=page)
                    logging.debug(f"Fetching proxies from {url}")
                    async with session.get(url, timeout=10) as response:
                        if response.status == 200:
                            data = await response.json()
                            proxies.extend([f"https://{proxy['ip']}:{proxy['port']}" for proxy in data.get('data', [])])
                        else:
                            logging.error(f"Failed to fetch proxies from API page {page}: HTTP {response.status}")
                self.proxies = proxies
                self.valid_proxies.extend(proxies)
                logging.info(f"Fetched {len(self.proxies)} HTTPS proxies from API")
                if not proxies:
                    logging.warning("No proxies fetched from API. Disabling proxies.")
                    self.use_proxy = False
        except Exception as e:
            logging.error(f"Error fetching proxies from API: {e}")
            self.use_proxy = False

    async def validate_proxy(self, proxy, test_url="https://httpbin.org/ip"):
        try:
            async with aiohttp.ClientSession() as session:
                logging.debug(f"Validating proxy: {proxy}")
                async with session.get(test_url, proxy=proxy, timeout=5, ssl=SSLVERIFY) as response:
                    if response.status == 200:
                        logging.debug(f"Proxy {proxy} is valid")
                        return True
            return False
        except Exception as e:
            logging.debug(f"Proxy {proxy} failed validation: {e}")
            return False

    async def pre_validate_proxies(self):
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
            else:
                logging.debug(f"Invalid proxy: {proxy}")
        self.valid_proxies[:] = valid
        logging.info(f"Validated {len(valid)} proxies")
        if not valid:
            logging.warning("No valid proxies available. Disabling proxies.")
            self.use_proxy = False

    def get_proxy(self):
        if not self.use_proxy or not self.valid_proxies:
            return None
        self.current_index = (self.current_index + 1) % len(self.valid_proxies)
        return self.valid_proxies[self.current_index]

    async def refresh_proxies(self):
        valid = []
        tasks = [self.validate_proxy(proxy) for proxy in self.valid_proxies]
        results = await asyncio.gather(*tasks, return_exceptions=True)
        for proxy, result in zip(list(self.valid_proxies), results):
            if result is True:
                valid.append(proxy)
            else:
                logging.debug(f"Removing invalid proxy: {proxy}")
        if len(valid) < len(self.valid_proxies) / 2:
            logging.info("Too many invalid proxies. Fetching new ones.")
            await self._fetch_proxies_from_api()
        else:
            self.valid_proxies[:] = valid
        logging.info(f"Refreshed {len(valid)} valid proxies")
        if not self.valid_proxies:
            logging.warning("No valid proxies available. Disabling proxies.")
            self.use_proxy = False

class LoadTester:
    def __init__(self, url, duration=DEFAULT_DURATION, sockets=DEFAULT_SOCKETS, max_threads=DEFAULT_WORKERS, request_timeout=5, endpoints=None, output_file=None, verbose=False, target_requests=None):
        self.url = url
        self.duration = duration
        self.sockets = sockets
        self.max_threads = max_threads
        self.request_timeout = request_timeout
        self.user_agents = USER_AGENTS
        self.manager = Manager()
        self.counter = self.manager.dict({'success': 0, 'failed': 0, '403': 0, 'status_codes': {}})
        self.response_times = self.manager.list()
        self.requests_in_window = self.manager.list()
        self.parsed = urllib.parse.urlparse(url)
        self.host = self.parsed.netloc.split(':')[0]
        self.ssl = self.parsed.scheme == 'https'
        self.endpoints = endpoints or ['/']
        self.output_file = output_file
        self.verbose = verbose
        self.target_requests = target_requests  # New: Target number of requests
        if not self.parsed.scheme or not self.parsed.netloc:
            raise ValueError("Invalid URL format. Include http:// or https://")

    def generate_random_query(self):
        params = {'q': str(random.randint(1, 1000)), 't': str(time.time())}
        return urllib.parse.urlencode(params)

    async def send_request(self, session, proxy_manager):
        headers = {
            'User-Agent': random.choice(self.user_agents),
            'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8',
            'Accept-Language': 'en-US,en;q=0.9',
            'Accept-Encoding': 'gzip, deflate',
            'Referer': f'{self.url}',
            'Connection': 'keep-alive',
            'Cache-Control': 'max-age=0',
            'DNT': '1',
        }
        proxy = proxy_manager.get_proxy() if proxy_manager and proxy_manager.use_proxy else None
        retries = 3
        method = 'GET'
        endpoint = random.choice(self.endpoints)
        url = f"{self.url.rstrip('/')}{endpoint}?{self.generate_random_query()}"
        logging.debug(f"Sending {method} to {url} with proxy {proxy or 'none'}")

        for attempt in range(1, retries + 1):
            try:
                start_time = time.time()
                async with session.get(
                    url,
                    headers=headers,
                    timeout=aiohttp.ClientTimeout(total=self.request_timeout),
                    ssl=SSLVERIFY,
                    proxy=proxy
                ) as response:
                    response_time = (time.time() - start_time) * 1000
                    self.counter['success'] += 1
                    self.counter['status_codes'][response.status] = self.counter['status_codes'].get(response.status, 0) + 1
                    if response.status == 403:
                        self.counter['403'] += 1
                        if proxy_manager and proxy_manager.use_proxy:
                            logging.debug(f"403 detected with proxy {proxy}. Rotating proxies.")
                            await proxy_manager.refresh_proxies()
                    self.response_times.append(response_time)
                    self.requests_in_window.append(time.time())
                    if self.verbose:
                        log_message = f"✓ Success {response.status} | Endpoint: {endpoint} | Proxy: {proxy or 'N'} | Time: {response_time:.2f}ms"
                        print(f"\033[92m{log_message}\033[0m")
                        if self.output_file:
                            with open(self.output_file, 'a', encoding='utf-8') as f:
                                f.write(f"[{time.strftime('%Y-%m-%d %H:%M:%S')}] {log_message}\n")
                    return True
            except aiohttp.ClientError as e:
                logging.error(f"Attempt {attempt} failed for {url} with proxy {proxy or 'none'}: {e}")
                if attempt < retries:
                    proxy = proxy_manager.get_proxy() if proxy_manager and proxy_manager.use_proxy else None
                    await asyncio.sleep(random.uniform(0.5, 1.5))
                    continue
                self.counter['failed'] += 1
                self.requests_in_window.append(time.time())
                if self.verbose:
                    log_message = f"✗ Error: {e} | Endpoint: {endpoint} | Proxy: {proxy or 'N'}"
                    print(f"\033[91m{log_message}\033[0m")
                    if self.output_file:
                        with open(self.output_file, 'a', encoding='utf-8') as f:
                            f.write(f"[{time.strftime('%Y-%m-%d %H:%M:%S')}] {log_message}\n")
                return False
        self.counter['failed'] += 1
        self.requests_in_window.append(time.time())
        logging.error(f"Max retries reached for {url}")
        return False

    async def display_stats(self, start_time, proxy_manager):
        while time.time() < start_time + self.duration:
            now = time.time()
            self.requests_in_window[:] = [t for t in self.requests_in_window if now - t <= 10]
            rps = len(self.requests_in_window) / 10 if self.requests_in_window else 0.0
            avg_response_time = sum(self.response_times) / len(self.response_times) if self.response_times else 0
            elapsed = int(now - start_time)
            remaining = int(self.duration - elapsed)
            proxies = len(proxy_manager.valid_proxies) if proxy_manager and proxy_manager.use_proxy else 0
            
            sys.stdout.write("\033[8F\033[J")  # Clear previous stats
            sys.stdout.write(
                f"\r{'='*40} Real-Time Stats {'='*40}\n"
                f"⏱  Elapsed: {elapsed}s | Remaining: {remaining}s\n"
                f"⚡ RPS: {rps:.1f}\n"
                f"✓ Success: {self.counter['success']} | ✗ Failed: {self.counter['failed']} | 403s: {self.counter['403']}\n"
                f"📊 Status Codes: {dict(self.counter['status_codes'])}\n"
                f"⏳ Avg Response Time: {avg_response_time:.1f} ms\n"
                f"🔗 Proxies: {proxies}\n"
                f"{'='*80}\n"
            )
            sys.stdout.flush()
            await asyncio.sleep(1)

    def print_custom_stats(self, total_time):
        """Custom function to print stats in the requested format."""
        total_attack = self.counter['success'] + self.counter['failed']
        print(f"\n✅ Load test completed")
        print("=" * 60)
        print(f"Total time: {total_time:.2f} seconds")
        print(f"Successful requests: {self.counter['success']}")
        print(f"Total attack: {total_attack}")
        if self.target_requests:
            print(f"Target requests: {self.target_requests}")
            print(f"Completion: {min(100, (total_attack/self.target_requests)*100):.1f}%")
        print("=" * 60)

    async def test(self, proxy_manager=None):
        print(f"\n🔶 Starting load test on {self.url}")
        print(f"Duration: {self.duration} seconds")
        print(f"Threads: {self.max_threads}")
        print(f"Sockets: {self.sockets}")
        print(f"Endpoints: {', '.join(self.endpoints)}")
        print(f"Output file: {self.output_file or 'None'}")
        print(f"Verbose: {self.verbose}")
        if self.target_requests:
            print(f"Target requests: {self.target_requests}")
        print("=" * 60)
        if proxy_manager and proxy_manager.use_proxy:
            print("🔍 Validating proxies...")
            await proxy_manager.pre_validate_proxies()
            print(f"✅ {len(proxy_manager.valid_proxies)} valid proxies ready")
        else:
            print("🔶 Running without proxies")
        
        start_time = time.time()
        connector = aiohttp.TCPConnector(limit=100, limit_per_host=50)  # Adjusted for performance
        session_retries = 3
        for attempt in range(1, session_retries + 1):
            try:
                async with aiohttp.ClientSession(cookie_jar=aiohttp.CookieJar(), connector=connector) as session:
                    stats_task = asyncio.create_task(self.display_stats(start_time, proxy_manager))
                    try:
                        while time.time() < start_time + self.duration:
                            # Check if we've reached our target number of requests (if specified)
                            if self.target_requests and (self.counter['success'] + self.counter['failed']) >= self.target_requests:
                                print("\n🎯 Target number of requests reached!")
                                break
                                
                            tasks = [self.send_request(session, proxy_manager) for _ in range(min(self.sockets, 100))]
                            await asyncio.gather(*tasks, return_exceptions=True)
                            await asyncio.sleep(random.uniform(0.3, 0.8))  # Adjusted for ~25 RPS
                            if proxy_manager and proxy_manager.use_proxy:
                                await proxy_manager.refresh_proxies()
                        stats_task.cancel()
                    except asyncio.CancelledError:
                        logging.warning("Test interrupted, cleaning up...")
                    except Exception as e:
                        logging.error(f"Test loop error: {e}")
                    finally:
                        await asyncio.sleep(0)  # Ensure stats task cancellation
                break
            except Exception as e:
                logging.error(f"Session initialization attempt {attempt} failed: {e}")
                if attempt < session_retries:
                    await asyncio.sleep(2)
                    continue
                print(f"\n❌ Failed to initialize session after {session_retries} attempts")
                return
        
        total_time = time.time() - start_time
        self.print_custom_stats(total_time)

def prompt_for_url():
    while True:
        url = input(f"Please enter a target URL (e.g., {DEFAULT_URL}, press Enter for default): ").strip()
        if not url:
            return DEFAULT_URL
        parsed = urllib.parse.urlparse(url)
        if parsed.scheme in ['http', 'https'] and parsed.netloc:
            return url
        print(f"❌ Error: Invalid URL format for {url}. Please include http:// or https://")

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
            target_input = input("Enter target number of requests (press Enter for no target): ").strip()
            if not target_input:
                return None
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

async def main():
    parser = argparse.ArgumentParser(
        description="HTTP Load Testing Tool for Authorized Use (Educational Use Only)",
        epilog="Examples:\n"
               "  python load_test.py https://example.com --useproxy --output results.txt --verbose\n"
               "  python load_test.py https://example.com --duration 60 --sockets 1000 --useproxy --endpoints /api,/search --output results.txt",
        formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument("url", nargs='?', help="Target URL (e.g., https://example.com)")
    parser.add_argument("-s", "--sockets", type=int, default=DEFAULT_SOCKETS, help="Number of sockets per cycle (default: 1000)")
    parser.add_argument("-t", "--timeout", type=int, default=5, help="Request timeout in seconds (default: 5)")
    parser.add_argument("--duration", type=int, default=DEFAULT_DURATION, help=f"Duration for test (default: {DEFAULT_DURATION})")
    parser.add_argument("--target", type=int, help="Target number of requests to complete")
    parser.add_argument("--useproxy", action="store_true", default=True, help="Use proxies with auto-rotation (default: True)")
    parser.add_argument("--proxy-file", default="proxies.txt", help="File containing proxies (default: proxies.txt)")
    parser.add_argument("--debug", action="store_true", help="Enable debug mode (disables SSL verification)")
    parser.add_argument("--endpoints", help="Comma-separated list of endpoints (e.g., /api,/search)")
    parser.add_argument("--output", help="File to save output (e.g., results.txt)")
    parser.add_argument("--verbose", action="store_true", help="Enable verbose per-request logging")
    args = parser.parse_args()

    global DEBUG, SSLVERIFY
    DEBUG = args.debug or DEBUG
    SSLVERIFY = not args.debug
    logging.basicConfig(
        format="[%(asctime)s] %(levelname)s: %(message)s",
        datefmt="%d-%m-%Y %H:%M:%S",
        level=logging.DEBUG if DEBUG else logging.INFO
    )

    url = args.url if args.url else prompt_for_url()
    endpoints = args.endpoints.split(',') if args.endpoints else prompt_for_endpoints()
    output_file = args.output if args.output else prompt_for_output_file()
    verbose = args.verbose or prompt_for_verbose()
    target_requests = args.target if args.target else prompt_for_target_requests()

    parsed = urllib.parse.urlparse(url)
    if not parsed.scheme or not parsed.netloc or parsed.scheme not in ['http', 'https']:
        print(f"❌ Error: Invalid URL format for {url}. Include http:// or https://")
        return

    proxy_manager = ProxyManager(proxy_file=args.proxy_file, use_proxy=args.useproxy)

    try:
        tester = LoadTester(
            url=url,
            duration=args.duration,
            sockets=args.sockets,
            max_threads=DEFAULT_WORKERS,
            request_timeout=args.timeout,
            endpoints=endpoints,
            output_file=output_file,
            verbose=verbose,
            target_requests=target_requests  # Pass target requests to LoadTester
        )
        await tester.test(proxy_manager)
    except ValueError as e:
        print(f"❌ Error for {url}: {e}")
    except Exception as e:
        print(f"❌ Unexpected error: {e}")
        logging.error(f"Main execution error: {e}")

if __name__ == "__main__":
    asyncio.run(main())
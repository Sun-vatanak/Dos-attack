
import requests
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from urllib.parse import urlparse
import random

USER_AGENTS = [
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:89.0) Gecko/20100101 Firefox/89.0",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/14.1.1 Safari/605.1.15"
]

def send_request(url, request_timeout=5):
    headers = {
        'User-Agent': random.choice(USER_AGENTS),
        'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8',
        'Accept-Language': 'en-US,en;q=0.5',
    }

    try:
        response = requests.get(
            url,
            headers=headers,
            timeout=request_timeout,
            allow_redirects=True
        )
        return {
            'status': response.status_code,
            'url': url,
            'success': True,
            'error': None
        }
    except Exception as e:
        return {
            'status': None,
            'url': url,
            'success': False,
            'error': str(e)
        }

def print_result(result, current, total):
    prefix = f"[{current}/{total}]"
    if result['success']:
        print(f"\033[92m{prefix} ✓ Success {result['status']}\033[0m | {result['url']}")
    else:
        print(f"\033[91m{prefix} ✗ Error: {result['error']}\033[0m | {result['url']}")

def load_test(url, total_requests=100, max_threads=10, request_delay=0.1, request_timeout=5):
    parsed = urlparse(url)
    if not parsed.scheme or not parsed.netloc:
        print("❌ Error: Invalid URL format. Please include http:// or https://")
        return

    print(f"\n🚀 Starting load test for: {url}")
    print(f"📨 Total requests: {total_requests}")
    print(f"🔗 Threads: {max_threads}")
    print(f"⏱️ Delay: {request_delay}s | Timeout: {request_timeout}s")
    print("=" * 60)

    start_time = time.time()
    success_count = 0
    failure_count = 0

    with ThreadPoolExecutor(max_workers=max_threads) as executor:
        futures = []
        for _ in range(total_requests):
            future = executor.submit(send_request, url, request_timeout)
            futures.append(future)
            time.sleep(request_delay)

        for i, future in enumerate(as_completed(futures), start=1):
            result = future.result()
            print_result(result, i, total_requests)
            if result['success']:
                success_count += 1
            else:
                failure_count += 1

    total_time = time.time() - start_time
    rps = total_requests / total_time if total_time > 0 else 0

    print("\n✅ Load test completed")
    print("=" * 60)
    print(f"⏱️ Total time: {total_time:.2f} seconds")
    print(f"🟢 Successful: {success_count}")
    print(f"🔴 Failed: {failure_count}")
    print(f"⚡ Requests per second: {rps:.2f} rps")
    print("=" * 60)

if __name__ == "__main__":
    print("🌐 Safe HTTP/HTTPS Load Tester")
    target_url = input("Enter target URL (e.g. https://test.com/): ").strip()

    if not target_url.startswith("http://") and not target_url.startswith("https://"):
        print("❌ Error: Invalid URL format. Please include http:// or https://")
    else:
        try:
            total = int(input("Enter total number of requests: "))
        except ValueError:
            print("❌ Invalid number. Using default of 100.")
            total = 100

        load_test(
            url=target_url,
            total_requests=total,
            max_threads=5,
            request_delay=0.1,
            request_timeout=5
        )

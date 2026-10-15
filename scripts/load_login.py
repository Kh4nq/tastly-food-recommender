"""Fire parallel bad logins at a LOCAL backend to see how it copes under load.

Run the backend first, with a single hash slot and a loose per-IP limit so the
503 from the hash gate is not hidden behind 429s (PowerShell):

    $env:BACKEND_WARMUP = "false"
    $env:BACKEND_AUTH_HASH_CONCURRENCY = "1"
    $env:BACKEND_AUTH_RATE_BURST = "1000"
    $env:BACKEND_AUTH_RATE_PER_MINUTE = "1000"
    .venv\\Scripts\\python.exe -m uvicorn backend.main:create_production_app --factory

Then: python scripts/load_login.py [-n 30]

Expected: a mix of 401 and 503, no request hanging for long, and /health still
answering fast while the hashes are running. Only talks to 127.0.0.1; it sends
credentials that cannot exist, so it creates nothing and locks no real account.
"""
import argparse
import json
import time
import urllib.error
import urllib.request
from collections import Counter
from concurrent.futures import ThreadPoolExecutor

URL = "http://127.0.0.1:8000"  # local dev only, on purpose not configurable
BODY = json.dumps({"email": "load-test@invalid.example", "password": "whatever"}).encode()


def login(_: int) -> tuple[int, float]:
    request = urllib.request.Request(
        URL + "/api/auth/login", BODY, {"Content-Type": "application/json"}
    )
    started = time.perf_counter()
    try:
        urllib.request.urlopen(request, timeout=20)
        code = 200
    except urllib.error.HTTPError as error:
        code = error.code
    return code, time.perf_counter() - started


def health() -> float:
    started = time.perf_counter()
    urllib.request.urlopen(URL + "/health", timeout=20).read()
    return time.perf_counter() - started


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("-n", type=int, default=30, help="parallel login requests")
    count = parser.parse_args().n

    with ThreadPoolExecutor(count + 10) as pool:
        logins = [pool.submit(login, i) for i in range(count)]
        time.sleep(0.5)  # let the hashes pile up, then ask something cheap
        probe = health()
        results = [f.result() for f in logins]

    print("status codes:", dict(sorted(Counter(code for code, _ in results).items())))
    print("slowest login: %.2fs" % max(took for _, took in results))
    print("/health while hashing: %.3fs" % probe)


if __name__ == "__main__":
    main()

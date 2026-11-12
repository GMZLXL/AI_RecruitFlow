import os
import urllib.request
from urllib.parse import urlsplit


def main():
    host = urlsplit(os.environ["APP_PUBLIC_URL"]).hostname
    request = urllib.request.Request("http://127.0.0.1:8000/api/v1/readyz", headers={"Host": host or "localhost"})
    with urllib.request.urlopen(request, timeout=3) as response:
        if response.status != 200:
            raise SystemExit(1)


if __name__ == "__main__":
    main()

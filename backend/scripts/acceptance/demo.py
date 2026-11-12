"""Start a NEW, no-key Mock database/API/web pair; never touches the ordinary .env/DB."""

import argparse
import base64
import json
import os
import shutil
import socket
import subprocess
import sys
import time
import uuid
from pathlib import Path

import httpx

BACKEND = Path(__file__).resolve().parents[2]
PROJECT = BACKEND.parent


def environment(root, api_port, web_port):
    # Fill EVERY connector field, including *_FILE, so development dotenv cannot import real secrets.
    env = os.environ.copy()
    for name in list(env):
        if name.startswith(("DEEPSEEK_", "TENCENT_", "WECOM_", "SSO_", "SESSION_", "APP_SECRET_")) or name == "DATABASE_URL_FILE":
            env.pop(name)
    for line in (BACKEND / ".env.example").read_text(encoding="utf-8").splitlines():
        if line and not line.startswith("#") and "=" in line:
            name, value = line.split("=", 1)
            env[name] = value
    for name in ("DATABASE_URL", "DEEPSEEK_API_KEY", "TENCENT_DOCS_TOKEN", "WECOM_SECRET", "WECOM_CALLBACK_TOKEN",
                 "WECOM_ENCODING_AES_KEY", "SESSION_CSRF_SECRET", "APP_SECRET_KEY"):
        env[name + "_FILE"] = ""
    env.update(APP_ENV="development", APP_MODE="mock", AUTH_MODE="dev", DEV_AUTH_ENABLED="true", DEV_DEFAULT_USER="admin",
        DATABASE_URL="sqlite:///" + (root / "demo.db").as_posix(),
        APP_SECRET_KEY=base64.urlsafe_b64encode(os.urandom(32)).decode(),
        ALLOWED_ORIGINS=f"http://127.0.0.1:{web_port}", RECRUITFLOW_API_TARGET=f"http://127.0.0.1:{api_port}",
        RECRUITFLOW_WEB_URL=f"http://127.0.0.1:{web_port}", RECRUITFLOW_API_URL=f"http://127.0.0.1:{api_port}/api/v1",
        RECRUITFLOW_WEB_BUILD="development")
    # This database is a disposable synthetic demonstration. No managed key will be saved by the script.
    return env


def stop(process):
    if process.poll() is not None:
        return
    if os.name == "nt":
        subprocess.run(["taskkill", "/PID", str(process.pid), "/T", "/F"], capture_output=True, check=False)
    else:
        process.terminate()
    try:
        process.wait(timeout=10)
    except subprocess.TimeoutExpired:
        process.kill()
        process.wait(timeout=5)


def wait_ready(url, process):
    with httpx.Client(trust_env=False, timeout=2) as client:
        deadline = time.monotonic() + 30
        while time.monotonic() < deadline:
            if process.poll() is not None:
                raise RuntimeError("Isolated service exited; see its local log")
            try:
                if client.get(url).status_code == 200:
                    return
            except httpx.TransportError:
                pass
            time.sleep(0.2)
    raise RuntimeError("Isolated service readiness timed out")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--api-port", type=int, default=8027)
    parser.add_argument("--web-port", type=int, default=5177)
    parser.add_argument("--verify", action="store_true", help="Seed fictional fixtures, run three HTTP smokes, then stop")
    args = parser.parse_args()
    if args.api_port == args.web_port or any(not 1024 <= port <= 65535 for port in (args.api_port, args.web_port)):
        parser.error("Choose two distinct local ports between 1024 and 65535")
    for port in (args.api_port, args.web_port):
        with socket.socket() as sock:
            sock.bind(("127.0.0.1", port))
    node = shutil.which("node")
    if not node:
        raise RuntimeError("Node.js is required")
    root = (PROJECT / ".tools" / ("s7-demo-" + uuid.uuid4().hex[:8])).resolve()
    root.mkdir(parents=True)
    env = environment(root, args.api_port, args.web_port)
    subprocess.run([sys.executable, "-m", "alembic", "upgrade", "head"], cwd=BACKEND, env=env, check=True)
    if args.verify:
        subprocess.run([sys.executable, "-m", "scripts.demo.seed"], cwd=BACKEND, env=env, check=True)
    processes = []
    info = {"mode": "mock", "api": env["RECRUITFLOW_API_URL"], "web": env["RECRUITFLOW_WEB_URL"], "artifacts": str(root)}
    (root / "run.json").write_text(json.dumps(info, indent=2), encoding="utf-8")
    with (root / "api.log").open("w", encoding="utf-8") as api_log, (root / "web.log").open("w", encoding="utf-8") as web_log:
        try:
            api = subprocess.Popen([sys.executable, "-m", "uvicorn", "app.main:app", "--host", "127.0.0.1", "--port", str(args.api_port), "--no-access-log", "--no-proxy-headers"],
                cwd=BACKEND, env=env, stdout=api_log, stderr=api_log)
            processes.append(api)
            wait_ready(info["api"] + "/readyz", api)
            web = subprocess.Popen([node, str(PROJECT / "node_modules/vite/bin/vite.js"), "--host", "127.0.0.1", "--port", str(args.web_port), "--strictPort"],
                cwd=PROJECT / "frontend", env=env, stdout=web_log, stderr=web_log)
            processes.append(web)
            wait_ready(info["web"], web)
            print(json.dumps(info, ensure_ascii=False), flush=True)
            if args.verify:
                for module in ("http", "workbench", "wecom"):
                    subprocess.run([sys.executable, "-m", "scripts.smoke." + module], cwd=BACKEND, env=env, check=True)
                (root / "http-result.json").write_text(json.dumps({"status": "passed", "checks": ["http", "workbench", "wecom"], **info}, indent=2), encoding="utf-8")
                print("PASS: isolated Mock HTTP release demonstration; no external providers")
            else:
                print("Empty synthetic database ready. Ctrl+C stops BOTH isolated services; artifacts remain ignored.", flush=True)
                while all(process.poll() is None for process in processes):
                    time.sleep(0.5)
                raise RuntimeError("An isolated service exited unexpectedly")
        except KeyboardInterrupt:
            pass
        finally:
            for process in reversed(processes):
                stop(process)


if __name__ == "__main__":
    main()

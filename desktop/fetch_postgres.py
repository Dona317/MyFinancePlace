"""
Download the portable PostgreSQL binaries for this platform into desktop/vendor/pgsql (build step of F16).

The binaries are the zonky.io "embedded-postgres-binaries" builds published on Maven Central: initdb, pg_ctl,
postgres and their libraries, for Windows, macOS (Intel and Apple Silicon) and Linux.

    python -m desktop.fetch_postgres            # this machine's platform
    python -m desktop.fetch_postgres --platform windows-amd64
"""
from __future__ import annotations

import argparse
import io
import platform
import shutil
import sys
import tarfile
import time
import urllib.error
import urllib.request
import zipfile
from pathlib import Path

VERSION = "16.15.0"
URL = ("https://repo1.maven.org/maven2/io/zonky/test/postgres/embedded-postgres-binaries-{platform}/{version}/"
       "embedded-postgres-binaries-{platform}-{version}.jar")
TARGET = Path(__file__).resolve().parent / "vendor" / "pgsql"


def this_platform() -> str:
    machine = platform.machine().lower()
    arm = machine in ("arm64", "aarch64")
    if sys.platform.startswith("win"):
        return "windows-amd64"
    if sys.platform == "darwin":
        return "darwin-arm64v8" if arm else "darwin-amd64"
    return "linux-arm64v8" if arm else "linux-amd64"


def fetch(name: str, target: Path = TARGET) -> Path:
    url = URL.format(platform=name, version=VERSION)
    print(f"downloading {url}")
    request = urllib.request.Request(url, headers={"User-Agent": "MyFinancePlace-build"})
    for attempt in range(5):
        try:
            with urllib.request.urlopen(request, timeout=300) as answer:  # noqa: S310 - fixed https URL
                jar = zipfile.ZipFile(io.BytesIO(answer.read()))
            break
        except urllib.error.HTTPError as exc:
            if exc.code not in (429, 502, 503) or attempt == 4:
                raise
            time.sleep(2 ** (attempt + 1))
    member = next(n for n in jar.namelist() if n.endswith(".txz"))
    if target.exists():
        shutil.rmtree(target)
    target.mkdir(parents=True)
    with tarfile.open(fileobj=io.BytesIO(jar.read(member)), mode="r:xz") as archive:
        archive.extractall(target, filter="data")
    print(f"PostgreSQL {VERSION} for {name} in {target}")
    return target


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--platform", default=this_platform())
    fetch(parser.parse_args().platform)

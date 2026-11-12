import argparse
import json
import os
import urllib.request

from .boundaries import pack
from .catalog import BOUNDARIES, COUNTRIES, prepare, public


def fetch_boundaries():
    BOUNDARIES.mkdir(parents=True, exist_ok=True)
    for code, (_, iso) in COUNTRIES.items():
        url = f"https://www.geoboundaries.org/api/current/gbOpen/{iso}/ADM1/"
        with urllib.request.urlopen(url, timeout=60) as response:
            meta = json.load(response)
        with urllib.request.urlopen(meta["gjDownloadURL"], timeout=120) as response:
            collection = json.load(response)
        pack(code, collection)
        destination = BOUNDARIES / f"{code}.source.json"
        temporary = destination.with_suffix(".tmp")
        temporary.write_text(json.dumps(meta))
        os.replace(temporary, destination)
        print(f"Installed {code} ADM1: {len(collection['features'])} features")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("command", choices=["prepare-data", "fetch-boundaries"])
    args = parser.parse_args()
    if args.command == "fetch-boundaries":
        fetch_boundaries()
        return
    releases = prepare(lambda _, message: print(message) if message else None)
    print(json.dumps([public(item) for item in releases.values()], indent=2))
    if any(item["status"] == "invalid" for item in releases.values()):
        raise SystemExit(1)


if __name__ == "__main__":
    main()

"""Separate lightweight rendering geometry from full-resolution selection geometry."""
import gzip
import hashlib
import json
from functools import lru_cache

import shapely
from shapely.geometry import mapping, shape

from .catalog import BOUNDARIES


def pack(code, collection):
    target = BOUNDARIES / code
    target.mkdir(parents=True, exist_ok=True)
    features = []
    for feature in collection["features"]:
        properties = feature["properties"]
        key = str(properties.get("shapeID") or feature.get("id") or properties["shapeName"])
        geom = shape(feature["geometry"])
        if not geom.is_valid:
            geom = shapely.make_valid(geom)
        filename = hashlib.sha256(key.encode()).hexdigest()[:24] + ".wkb.gz"
        temporary = target / (filename + ".tmp")
        temporary.write_bytes(gzip.compress(shapely.to_wkb(geom), compresslevel=5))
        temporary.replace(target / filename)
        features.append({
            "type": "Feature", "id": key, "properties": {
                "name": properties.get("shapeName", key), "file": filename,
            },
            "geometry": mapping(geom.simplify(0.014, preserve_topology=True)),
        })
    temporary = target / "regions.tmp"
    temporary.write_text(json.dumps({"type": "FeatureCollection", "features": features},
                                    separators=(",", ":")))
    temporary.replace(target / "regions.json")


@lru_cache(maxsize=4)
def read_packed(path, version):
    return json.loads(path.read_text())


@lru_cache(maxsize=6)
def read_geometry(path, version):
    return shapely.from_wkb(gzip.decompress(path.read_bytes()))

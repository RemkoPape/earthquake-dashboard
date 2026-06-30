from __future__ import annotations

import csv
import hashlib
import io
import json
import os
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Dict, Iterable, List, Tuple
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen


ROOT_DIR = Path(__file__).resolve().parent.parent
DATA_DIR = ROOT_DIR / "wildfires" / "data"
ARCHIVE_PATH = DATA_DIR / "archive.geojson"

FIRMS_SOURCES = {
  "VIIRS_SNPP_NRT": "Suomi-NPP",
  "VIIRS_NOAA20_NRT": "NOAA-20",
  "VIIRS_NOAA21_NRT": "NOAA-21",
}

OUTPUT_WINDOWS: List[Tuple[str, timedelta, str]] = [
  ("fires-24h.geojson", timedelta(days=1), "Past 24 hours"),
  ("fires-3d.geojson", timedelta(days=3), "Past 3 days"),
  ("fires-5d.geojson", timedelta(days=5), "Past 5 days"),
  ("fires-30d.geojson", timedelta(days=30), "Past 30 days"),
  ("fires-90d.geojson", timedelta(days=90), "Past 90 days"),
]

DISCLAIMER = (
  "Satellite-detected active fire / thermal anomaly observations are not "
  "official wildfire perimeters and may include agricultural burning, "
  "industrial heat sources, volcanoes, gas flares, or other thermal anomalies."
)


def load_env_file(path: Path) -> None:
  if not path.exists():
    return

  for raw_line in path.read_text(encoding="utf-8").splitlines():
    line = raw_line.strip()
    if not line or line.startswith("#"):
      continue
    if line.startswith("export "):
      line = line[7:].strip()
    if "=" not in line:
      continue

    key, value = line.split("=", 1)
    key = key.strip()
    value = value.strip().strip('"').strip("'")
    if key and key not in os.environ:
      os.environ[key] = value


load_env_file(ROOT_DIR / ".env")


def utc_now() -> datetime:
  return datetime.now(timezone.utc)


def parse_float(value: str | None) -> float | None:
  if value in (None, ""):
    return None
  try:
    return float(value)
  except ValueError:
    return None


def parse_acq_datetime(acq_date: str | None, acq_time: str | None) -> datetime | None:
  if not acq_date:
    return None

  time_text = str(acq_time or "0000").strip().zfill(4)
  hour = int(time_text[:2])
  minute = int(time_text[2:])

  try:
    parsed = datetime.strptime(acq_date, "%Y-%m-%d")
  except ValueError:
    return None

  return parsed.replace(hour=hour, minute=minute, tzinfo=timezone.utc)


def normalize_confidence(raw_value: str | None) -> Tuple[str, str]:
  if raw_value is None:
    return "Unknown", "unknown"

  text = str(raw_value).strip()
  lowered = text.lower()

  if lowered in {"h", "high"}:
    return "High", "high"
  if lowered in {"n", "nominal"}:
    return "Nominal", "nominal"
  if lowered in {"l", "low"}:
    return "Low", "low"

  try:
    numeric = float(lowered)
  except ValueError:
    return text, lowered or "unknown"

  if numeric >= 80:
    return f"{numeric:g}", "high"
  if numeric >= 30:
    return f"{numeric:g}", "nominal"
  return f"{numeric:g}", "low"


def intensity_class_for_frp(frp: float | None) -> str:
  if frp is None or frp < 10:
    return "low"
  if frp < 50:
    return "moderate"
  if frp < 150:
    return "high"
  return "extreme"


def normalize_daynight(raw_value: str | None) -> str:
  if not raw_value:
    return "Unknown"
  lowered = str(raw_value).strip().lower()
  if lowered == "d":
    return "Day"
  if lowered == "n":
    return "Night"
  return str(raw_value)


def feature_identifier(properties: Dict[str, object]) -> str:
  identity = "|".join(
    str(properties.get(key, ""))
    for key in (
      "source",
      "acq_datetime_utc",
      "latitude",
      "longitude",
      "frp",
      "brightness",
      "daynight",
    )
  )
  return hashlib.sha1(identity.encode("utf-8")).hexdigest()


def row_to_feature(row: Dict[str, str], source_name: str, fetched_at: datetime) -> Dict[str, object] | None:
  latitude = parse_float(row.get("latitude"))
  longitude = parse_float(row.get("longitude"))
  acquisition = parse_acq_datetime(row.get("acq_date"), row.get("acq_time"))

  if latitude is None or longitude is None or acquisition is None:
    return None

  brightness = (
    parse_float(row.get("brightness"))
    or parse_float(row.get("bright_ti4"))
    or parse_float(row.get("bright_t31"))
  )
  frp = parse_float(row.get("frp"))
  confidence, confidence_class = normalize_confidence(row.get("confidence"))
  intensity_class = intensity_class_for_frp(frp)
  age_hours = max(0.0, round((fetched_at - acquisition).total_seconds() / 3600, 2))

  properties: Dict[str, object] = {
    "latitude": latitude,
    "longitude": longitude,
    "acq_date": row.get("acq_date") or "",
    "acq_time": str(row.get("acq_time") or "").zfill(4),
    "acq_datetime_utc": acquisition.isoformat().replace("+00:00", "Z"),
    "satellite": FIRMS_SOURCES[source_name],
    "instrument": row.get("instrument") or "VIIRS",
    "confidence": confidence,
    "brightness": brightness,
    "frp": frp,
    "daynight": normalize_daynight(row.get("daynight")),
    "source": source_name,
    "age_hours": age_hours,
    "intensity_class": intensity_class,
    "confidence_class": confidence_class,
  }

  feature_id = feature_identifier(properties)

  return {
    "type": "Feature",
    "id": feature_id,
    "geometry": {
      "type": "Point",
      "coordinates": [longitude, latitude],
    },
    "properties": properties,
  }


def fetch_source_rows(map_key: str, source_name: str) -> List[Dict[str, str]]:
  url = f"https://firms.modaps.eosdis.nasa.gov/api/area/csv/{map_key}/{source_name}/world/5"
  request = Request(url, headers={"User-Agent": "dashboard-hub-fire-updater/1.0"})

  try:
    with urlopen(request, timeout=90) as response:
      payload = response.read().decode("utf-8-sig")
  except HTTPError as error:
    raise RuntimeError(f"FIRMS request failed for {source_name}: HTTP {error.code}") from error
  except URLError as error:
    raise RuntimeError(f"FIRMS request failed for {source_name}: {error.reason}") from error

  return list(csv.DictReader(io.StringIO(payload)))


def load_existing_archive() -> List[Dict[str, object]]:
  if not ARCHIVE_PATH.exists():
    return []

  with ARCHIVE_PATH.open("r", encoding="utf-8") as handle:
    payload = json.load(handle)

  features = payload.get("features")
  return features if isinstance(features, list) else []


def parse_feature_datetime(feature: Dict[str, object]) -> datetime | None:
  properties = feature.get("properties", {})
  timestamp = properties.get("acq_datetime_utc")
  if not timestamp:
    return None

  try:
    return datetime.fromisoformat(str(timestamp).replace("Z", "+00:00"))
  except ValueError:
    return None


def within_archive_window(feature: Dict[str, object], cutoff: datetime) -> bool:
  timestamp = parse_feature_datetime(feature)
  return bool(timestamp and timestamp >= cutoff)


def merge_features(existing: Iterable[Dict[str, object]], incoming: Iterable[Dict[str, object]], fetched_at: datetime) -> List[Dict[str, object]]:
  cutoff = fetched_at - timedelta(days=90)
  merged: Dict[str, Dict[str, object]] = {}

  for feature in existing:
    if not within_archive_window(feature, cutoff):
      continue
    feature_id = feature.get("id") or feature_identifier(feature.get("properties", {}))
    feature["id"] = feature_id
    merged[str(feature_id)] = feature

  for feature in incoming:
    feature_id = feature.get("id") or feature_identifier(feature.get("properties", {}))
    feature["id"] = feature_id
    merged[str(feature_id)] = feature

  features = list(merged.values())
  features.sort(
    key=lambda item: parse_feature_datetime(item) or datetime.min.replace(tzinfo=timezone.utc),
    reverse=True,
  )
  return features


def features_for_window(features: Iterable[Dict[str, object]], generated_at: datetime, window: timedelta) -> List[Dict[str, object]]:
  cutoff = generated_at - window
  return [
    feature
    for feature in features
    if within_archive_window(feature, cutoff)
  ]


def source_counts(features: Iterable[Dict[str, object]]) -> Dict[str, int]:
  counts: Dict[str, int] = {source_name: 0 for source_name in FIRMS_SOURCES}
  for feature in features:
    source_name = feature.get("properties", {}).get("source")
    if source_name in counts:
      counts[source_name] += 1
  return counts


def build_collection(features: List[Dict[str, object]], generated_at: datetime, period_label: str) -> Dict[str, object]:
  return {
    "type": "FeatureCollection",
    "metadata": {
      "generated_at_utc": generated_at.isoformat().replace("+00:00", "Z"),
      "period_label": period_label,
      "feature_count": len(features),
      "source_counts": source_counts(features),
      "disclaimer": DISCLAIMER,
    },
    "features": features,
  }


def write_json(path: Path, payload: Dict[str, object]) -> None:
  path.parent.mkdir(parents=True, exist_ok=True)
  with path.open("w", encoding="utf-8", newline="\n") as handle:
    json.dump(payload, handle, indent=2)
    handle.write("\n")


def main() -> int:
  map_key = os.environ.get("FIRMS_MAP_KEY")
  if not map_key:
    print("FIRMS_MAP_KEY is required.", file=sys.stderr)
    return 1

  generated_at = utc_now()
  DATA_DIR.mkdir(parents=True, exist_ok=True)

  fetched_features: List[Dict[str, object]] = []
  for source_name in FIRMS_SOURCES:
    rows = fetch_source_rows(map_key, source_name)
    for row in rows:
      feature = row_to_feature(row, source_name, generated_at)
      if feature is not None:
        fetched_features.append(feature)

  archive_features = merge_features(load_existing_archive(), fetched_features, generated_at)
  write_json(ARCHIVE_PATH, build_collection(archive_features, generated_at, "Rolling 90-day archive"))

  for file_name, window, label in OUTPUT_WINDOWS:
    window_features = features_for_window(archive_features, generated_at, window)
    write_json(DATA_DIR / file_name, build_collection(window_features, generated_at, label))

  print(
    f"Updated wildfire archive with {len(archive_features)} detections at "
    f"{generated_at.isoformat().replace('+00:00', 'Z')}"
  )
  return 0


if __name__ == "__main__":
  raise SystemExit(main())

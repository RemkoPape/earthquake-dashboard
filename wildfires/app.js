const DATASETS = {
  "24h": {
    label: "Past 24 hours",
    dayRange: 1
  },
  "3d": {
    label: "Past 3 days",
    dayRange: 3
  },
  "5d": {
    label: "Past 5 days",
    dayRange: 5
  }
};

const FIRMS_SOURCES = {
  VIIRS_SNPP_NRT: "Suomi-NPP",
  VIIRS_NOAA20_NRT: "NOAA-20",
  VIIRS_NOAA21_NRT: "NOAA-21"
};

const INTENSITY_COLOURS = {
  low: "#f7d154",
  moderate: "#ff9a3d",
  high: "#ff5c39",
  extreme: "#d7263d"
};

const INTENSITY_LABELS = {
  low: "Low",
  moderate: "Moderate",
  high: "High",
  extreme: "Extreme"
};

const SATELLITE_LABELS = {
  "Suomi-NPP": "Suomi-NPP",
  "NOAA-20": "NOAA-20",
  "NOAA-21": "NOAA-21"
};

const QUICK_ADD_IMPORT_URI =
  "obsidian://adv-uri?vault=Life&commandid=quickadd%3Achoice%3A395808e2-6330-4744-af7e-6daf734002c3";

const FIRMS_SOURCE_URL = "https://firms.modaps.eosdis.nasa.gov/";
const FIRMS_MAP_KEY = window.WILDFIRE_CONFIG && window.WILDFIRE_CONFIG.FIRMS_MAP_KEY
  ? String(window.WILDFIRE_CONFIG.FIRMS_MAP_KEY)
  : "";

const state = {
  period: "3d",
  intensity: "all",
  confidence: "nominal_high",
  satellite: "all",
  cache: new Map(),
  currentCollection: null,
  activeRequestId: 0
};

const elements = {
  periodSelect: document.getElementById("periodSelect"),
  intensitySelect: document.getElementById("intensitySelect"),
  confidenceSelect: document.getElementById("confidenceSelect"),
  satelliteSelect: document.getElementById("satelliteSelect"),
  visibleCount: document.getElementById("visibleCount"),
  highestFrp: document.getElementById("highestFrp"),
  extremeCount: document.getElementById("extremeCount"),
  lastUpdate: document.getElementById("lastUpdate"),
  statusPanel: document.getElementById("statusPanel")
};

const map = new maplibregl.Map({
  container: "map",
  style: {
    version: 8,
    sources: {
      osm: {
        type: "raster",
        tiles: ["https://tile.openstreetmap.org/{z}/{x}/{y}.png"],
        tileSize: 256,
        attribution: "© OpenStreetMap contributors"
      }
    },
    layers: [
      {
        id: "osm",
        type: "raster",
        source: "osm",
        paint: {
          "raster-saturation": -0.45,
          "raster-brightness-min": 0.05,
          "raster-brightness-max": 0.92
        }
      }
    ]
  },
  center: [15, 20],
  zoom: 1.35
});

map.addControl(new maplibregl.NavigationControl(), "top-right");

function formatValue(value, fallback = "not available") {
  if (value === null || value === undefined || value === "") return fallback;
  return value;
}

function escapeHtml(value) {
  return String(value)
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;")
    .replace(/'/g, "&#39;");
}

function formatUtcDateTime(value) {
  if (!value) return "not available";
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return "not available";
  return date.toISOString().replace("T", " ").slice(0, 16) + " UTC";
}

function formatLastUpdate(value) {
  if (!value) return "no data";
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return "no data";
  return date.toLocaleString([], {
    month: "short",
    day: "numeric",
    hour: "2-digit",
    minute: "2-digit"
  });
}

function formatAgeHours(value) {
  const hours = Number(value);
  if (!Number.isFinite(hours)) return "not available";
  if (hours < 24) return `${hours.toFixed(1)} h`;
  return `${(hours / 24).toFixed(1)} d`;
}

function formatCoordinate(value) {
  const number = Number(value);
  if (!Number.isFinite(number)) return "not available";
  return number.toFixed(4);
}

function formatFrp(value) {
  const number = Number(value);
  if (!Number.isFinite(number)) return "not available";
  return `${number.toFixed(1)} MW`;
}

function formatBrightness(value) {
  const number = Number(value);
  if (!Number.isFinite(number)) return "not available";
  return `${number.toFixed(1)} K`;
}

function frontMatterScalar(value) {
  if (value === null || value === undefined || value === "") return "";
  return String(value);
}

function setStatusMessage(message = "") {
  if (!elements.statusPanel) return;
  elements.statusPanel.hidden = !message;
  elements.statusPanel.textContent = message;
}

function parseFloatOrNull(value) {
  if (value === null || value === undefined || value === "") return null;
  const parsed = Number.parseFloat(value);
  return Number.isFinite(parsed) ? parsed : null;
}

function parseAcqDateTime(acqDate, acqTime) {
  if (!acqDate) return null;
  const timeText = String(acqTime || "0000").trim().padStart(4, "0");
  const parsed = new Date(`${acqDate}T${timeText.slice(0, 2)}:${timeText.slice(2, 4)}:00Z`);
  return Number.isNaN(parsed.getTime()) ? null : parsed;
}

function normalizeConfidence(rawValue) {
  if (rawValue === null || rawValue === undefined || rawValue === "") {
    return { label: "Unknown", className: "unknown" };
  }

  const text = String(rawValue).trim();
  const lowered = text.toLowerCase();
  if (lowered === "h" || lowered === "high") return { label: "High", className: "high" };
  if (lowered === "n" || lowered === "nominal") return { label: "Nominal", className: "nominal" };
  if (lowered === "l" || lowered === "low") return { label: "Low", className: "low" };

  const numeric = Number.parseFloat(lowered);
  if (!Number.isFinite(numeric)) return { label: text, className: lowered || "unknown" };
  if (numeric >= 80) return { label: `${numeric}`, className: "high" };
  if (numeric >= 30) return { label: `${numeric}`, className: "nominal" };
  return { label: `${numeric}`, className: "low" };
}

function normalizeDayNight(rawValue) {
  if (!rawValue) return "Unknown";
  const lowered = String(rawValue).trim().toLowerCase();
  if (lowered === "d") return "Day";
  if (lowered === "n") return "Night";
  return String(rawValue);
}

function featureIdentifier(properties) {
  return [
    properties.source,
    properties.acq_datetime_utc,
    properties.latitude,
    properties.longitude,
    properties.frp,
    properties.brightness,
    properties.daynight
  ].join("|");
}

function parseCsv(text) {
  const normalized = String(text || "").replace(/\r\n/g, "\n").replace(/\r/g, "\n");
  const lines = normalized.split("\n").filter((line) => line.trim() !== "");
  if (!lines.length) return [];

  function splitCsvLine(line) {
    const values = [];
    let current = "";
    let inQuotes = false;

    for (let index = 0; index < line.length; index += 1) {
      const char = line[index];
      const next = line[index + 1];
      if (char === "\"") {
        if (inQuotes && next === "\"") {
          current += "\"";
          index += 1;
        } else {
          inQuotes = !inQuotes;
        }
      } else if (char === "," && !inQuotes) {
        values.push(current);
        current = "";
      } else {
        current += char;
      }
    }

    values.push(current);
    return values;
  }

  const headers = splitCsvLine(lines[0]).map((header) => header.trim());
  return lines.slice(1).map((line) => {
    const values = splitCsvLine(line);
    const row = {};
    headers.forEach((header, index) => {
      row[header] = values[index] ?? "";
    });
    return row;
  });
}

function rowToFeature(row, sourceName, fetchedAt) {
  const latitude = parseFloatOrNull(row.latitude);
  const longitude = parseFloatOrNull(row.longitude);
  const acquisition = parseAcqDateTime(row.acq_date, row.acq_time);
  if (latitude === null || longitude === null || !acquisition) return null;

  const brightness = parseFloatOrNull(row.brightness)
    ?? parseFloatOrNull(row.bright_ti4)
    ?? parseFloatOrNull(row.bright_t31);
  const frp = parseFloatOrNull(row.frp);
  const confidence = normalizeConfidence(row.confidence);
  const intensityClass = intensityClassForFrp(frp);
  const ageHours = Math.max(0, Math.round(((fetchedAt.getTime() - acquisition.getTime()) / 3600000) * 100) / 100);

  const properties = {
    latitude,
    longitude,
    acq_date: row.acq_date || "",
    acq_time: String(row.acq_time || "").padStart(4, "0"),
    acq_datetime_utc: acquisition.toISOString(),
    satellite: FIRMS_SOURCES[sourceName] || sourceName,
    instrument: row.instrument || "VIIRS",
    confidence: confidence.label,
    brightness,
    frp,
    daynight: normalizeDayNight(row.daynight),
    source: sourceName,
    age_hours: ageHours,
    intensity_class: intensityClass,
    confidence_class: confidence.className
  };

  return {
    type: "Feature",
    id: featureIdentifier(properties),
    geometry: {
      type: "Point",
      coordinates: [longitude, latitude]
    },
    properties
  };
}

function buildLiveCollection(features, periodLabel, generatedAt) {
  const sourceCounts = Object.fromEntries(
    Object.keys(FIRMS_SOURCES).map((sourceName) => [sourceName, 0])
  );

  features.forEach((feature) => {
    const sourceName = feature.properties && feature.properties.source;
    if (sourceName in sourceCounts) sourceCounts[sourceName] += 1;
  });

  return {
    type: "FeatureCollection",
    metadata: {
      generated_at_utc: generatedAt.toISOString(),
      period_label: periodLabel,
      feature_count: features.length,
      source_counts: sourceCounts,
      disclaimer: "Satellite-detected active fire / thermal anomaly observations are not official wildfire perimeters and may include agricultural burning, industrial heat sources, volcanoes, gas flares, or other thermal anomalies."
    },
    features
  };
}

function safeFileName(text) {
  return String(text)
    .replace(/[\\/:*?"<>|]/g, "")
    .replace(/\s+/g, " ")
    .trim()
    .slice(0, 120);
}

function intensityClassForFrp(frp) {
  const value = Number(frp);
  if (!Number.isFinite(value)) return "low";
  if (value < 10) return "low";
  if (value < 50) return "moderate";
  if (value < 150) return "high";
  return "extreme";
}

function colourForIntensity(intensityClass) {
  return INTENSITY_COLOURS[intensityClass] || "#f7d154";
}

function radiusForIntensity(intensityClass, frp) {
  const base = {
    low: 6,
    moderate: 8,
    high: 11,
    extreme: 15
  }[intensityClass] || 6;
  const frpValue = Number(frp);
  if (!Number.isFinite(frpValue)) return base;
  return Math.max(base, Math.min(base + Math.sqrt(frpValue) * 0.45, base + 10));
}

function opacityForAge(ageHours) {
  const age = Number(ageHours);
  if (!Number.isFinite(age)) return 0.78;
  if (age <= 24) return 0.92;
  if (age <= 72) return 0.78;
  if (age <= 120) return 0.62;
  if (age <= 720) return 0.42;
  return 0.24;
}

function glowOpacityForAge(ageHours) {
  return Math.max(0.08, opacityForAge(ageHours) * 0.26);
}

function confidenceMatches(properties) {
  const confidenceClass = String(properties.confidence_class || "").toLowerCase();
  if (state.confidence === "all") return true;
  if (state.confidence === "high_only") return confidenceClass === "high";
  return confidenceClass === "nominal" || confidenceClass === "high";
}

function intensityMatches(properties) {
  if (state.intensity === "all") return true;
  return String(properties.intensity_class || "").toLowerCase() === state.intensity;
}

function satelliteMatches(properties) {
  if (state.satellite === "all") return true;
  return String(properties.satellite || "") === state.satellite;
}

function normalizeFeature(feature) {
  const properties = { ...(feature.properties || {}) };
  const coordinates = feature.geometry && Array.isArray(feature.geometry.coordinates)
    ? feature.geometry.coordinates
    : [properties.longitude, properties.latitude];

  const intensityClass = String(
    properties.intensity_class || intensityClassForFrp(properties.frp)
  ).toLowerCase();
  const confidenceClass = String(properties.confidence_class || "").toLowerCase();
  const markerRadius = radiusForIntensity(intensityClass, properties.frp);
  const markerOpacity = opacityForAge(properties.age_hours);

  return {
    type: "Feature",
    id: feature.id || properties.id || null,
    geometry: {
      type: "Point",
      coordinates: [
        Number(coordinates[0]),
        Number(coordinates[1])
      ]
    },
    properties: {
      ...properties,
      intensity_class: intensityClass,
      intensity_label: INTENSITY_LABELS[intensityClass] || "Low",
      confidence_class: confidenceClass,
      marker_colour: colourForIntensity(intensityClass),
      marker_radius: markerRadius,
      marker_opacity: markerOpacity,
      glow_opacity: glowOpacityForAge(properties.age_hours),
      marker_stroke: "rgba(255,255,255,0.9)"
    }
  };
}

function filteredFeaturesFrom(collection) {
  const features = Array.isArray(collection.features) ? collection.features : [];
  return features
    .map(normalizeFeature)
    .filter((feature) =>
      intensityMatches(feature.properties) &&
      confidenceMatches(feature.properties) &&
      satelliteMatches(feature.properties)
    );
}

function buildDisplayCollection(features, metadata = {}) {
  return {
    type: "FeatureCollection",
    metadata,
    features
  };
}

function updateStats(collection) {
  const features = Array.isArray(collection.features) ? collection.features : [];
  const maxFrp = features.reduce((maxValue, feature) => {
    const frp = Number(feature.properties.frp);
    return Number.isFinite(frp) ? Math.max(maxValue, frp) : maxValue;
  }, 0);
  const extremeCount = features.filter(
    (feature) => feature.properties.intensity_class === "extreme"
  ).length;

  elements.visibleCount.textContent = String(features.length);
  elements.highestFrp.textContent = `${maxFrp.toFixed(1)} MW`;
  elements.extremeCount.textContent = String(extremeCount);
  elements.lastUpdate.textContent = formatLastUpdate(collection.metadata.generated_at_utc);
}

function setMapData(collection) {
  updateStats(collection);

  if (!map.getSource("fires")) return;
  map.getSource("fires").setData(collection);
}

function buildPopupHtml(properties, coordinates) {
  const intensityClass = String(properties.intensity_class || "low").toLowerCase();
  const headerColour = colourForIntensity(intensityClass);
  const title = `${formatValue(properties.intensity_label, "Low")} active fire / thermal anomaly`;

  return `
    <div class="fire-popup">
      <div class="fire-popup-header" style="background:${headerColour}">
        <h2>${escapeHtml(title)}</h2>
        <div class="subtitle">${escapeHtml(formatValue(properties.source, "NASA FIRMS"))}</div>
      </div>

      <div class="fire-popup-body">
        <div class="popup-grid">
          <div class="popup-metric">
            <span>Detection time UTC</span>
            <strong>${escapeHtml(formatUtcDateTime(properties.acq_datetime_utc))}</strong>
          </div>

          <div class="popup-metric">
            <span>FRP</span>
            <strong>${escapeHtml(formatFrp(properties.frp))}</strong>
          </div>

          <div class="popup-metric">
            <span>Latitude / longitude</span>
            <strong>${escapeHtml(`${formatCoordinate(coordinates[1])}, ${formatCoordinate(coordinates[0])}`)}</strong>
          </div>

          <div class="popup-metric">
            <span>Brightness temperature</span>
            <strong>${escapeHtml(formatBrightness(properties.brightness))}</strong>
          </div>

          <div class="popup-metric">
            <span>Satellite</span>
            <strong>${escapeHtml(formatValue(properties.satellite))}</strong>
          </div>

          <div class="popup-metric">
            <span>Instrument</span>
            <strong>${escapeHtml(formatValue(properties.instrument))}</strong>
          </div>

          <div class="popup-metric">
            <span>Confidence</span>
            <strong>${escapeHtml(formatValue(properties.confidence))}</strong>
          </div>

          <div class="popup-metric">
            <span>Day / night</span>
            <strong>${escapeHtml(formatValue(properties.daynight))}</strong>
          </div>

          <div class="popup-metric">
            <span>Intensity class</span>
            <strong>${escapeHtml(formatValue(properties.intensity_label))}</strong>
          </div>

          <div class="popup-metric">
            <span>Detection age</span>
            <strong>${escapeHtml(formatAgeHours(properties.age_hours))}</strong>
          </div>
        </div>

        <a class="popup-link" href="${FIRMS_SOURCE_URL}" target="_blank" rel="noopener">
          Open NASA FIRMS source
        </a>

        <button class="popup-button" id="obsidian-note-button">
          Create Obsidian note
        </button>

        <button class="popup-button secondary" id="copy-markdown-button">
          Copy note markdown
        </button>

        <button class="popup-button secondary" id="copy-import-button">
          Copy + import to Obsidian
        </button>
      </div>
    </div>
  `;
}

function createObsidianMarkdown(properties, coordinates) {
  const lat = Number(coordinates[1]);
  const lon = Number(coordinates[0]);
  const eventDate = properties.acq_datetime_utc
    ? String(properties.acq_datetime_utc).slice(0, 10)
    : "";
  const frpValue = formatFrp(properties.frp);
  const brightness = formatBrightness(properties.brightness);
  const intensity = formatValue(properties.intensity_label, "Low");
  const confidence = formatValue(properties.confidence);
  const title = `${intensity} active fire / thermal anomaly at ${lat.toFixed(3)}, ${lon.toFixed(3)}`;

  return `---
Date: ${eventDate}
Link: ${FIRMS_SOURCE_URL}
aliases:
  - "${title}"
Source: "[[NASA FIRMS]]"
Detection_time_utc: ${frontMatterScalar(properties.acq_datetime_utc)}
Satellite: ${frontMatterScalar(properties.satellite)}
Instrument: ${frontMatterScalar(properties.instrument)}
Confidence: ${confidence}
Intensity_class: ${intensity}
FRP_MW: ${frontMatterScalar(properties.frp)}
Brightness_K: ${frontMatterScalar(properties.brightness)}
DayNight: ${frontMatterScalar(properties.daynight)}
Location: ${lat},${lon}
tags:
  - Geoscience
  - Geohazards
  - Wildfire
  - NASA-FIRMS
---

# ${title}

## Quick summary

This note records a satellite-detected active fire / thermal anomaly observation from [[NASA FIRMS]] for later linking, review, and context building.

The detection was observed on **${formatUtcDateTime(properties.acq_datetime_utc)}** by **${formatValue(properties.satellite)}** (${formatValue(properties.instrument)}) with **${confidence.toLowerCase()} confidence** and a Fire Radiative Power of **${frpValue}**.

## Detection details

| Field | Value |
|---|---|
| Detection time UTC | ${formatUtcDateTime(properties.acq_datetime_utc)} |
| Latitude | ${lat.toFixed(4)} |
| Longitude | ${lon.toFixed(4)} |
| Satellite | ${formatValue(properties.satellite)} |
| Instrument | ${formatValue(properties.instrument)} |
| Confidence | ${confidence} |
| FRP | ${frpValue} |
| Brightness temperature | ${brightness} |
| Day / night | ${formatValue(properties.daynight)} |
| Intensity class | ${intensity} |
| Detection age | ${formatAgeHours(properties.age_hours)} |

## Interpretation note

These data represent a satellite-detected active fire / thermal anomaly and are **not** official wildfire perimeter mapping. Agricultural burning, industrial heat sources, volcanoes, gas flares, and other thermal anomalies may also appear in this dataset.

## Notes


## Reference

[^1]: [NASA FIRMS active fire data](${FIRMS_SOURCE_URL})
`;
}

function openEventInObsidian(properties, coordinates) {
  const markdown = createObsidianMarkdown(properties, coordinates);
  const timestamp = properties.acq_datetime_utc
    ? String(properties.acq_datetime_utc).slice(0, 10)
    : "unknown-date";
  const fileName = safeFileName(
    `Active Fire - ${properties.satellite ?? "Unknown"} - ${timestamp} - ${formatCoordinate(coordinates[1])}, ${formatCoordinate(coordinates[0])}`
  );
  const obsidianUrl =
    "obsidian://new?" +
    "name=" + encodeURIComponent(fileName) +
    "&content=" + encodeURIComponent(markdown);

  window.open(obsidianUrl, obsidianUrl);
}

async function copyEventMarkdown(properties, coordinates) {
  const markdown = createObsidianMarkdown(properties, coordinates);

  try {
    await navigator.clipboard.writeText(markdown);
    alert("Wildfire note copied. Paste it into Obsidian.");
  } catch (error) {
    console.error(error);
    const textArea = document.createElement("textarea");
    textArea.value = markdown;
    document.body.appendChild(textArea);
    textArea.select();

    try {
      document.execCommand("copy");
      alert("Wildfire note copied. Paste it into Obsidian.");
    } catch (fallbackError) {
      alert("Could not copy automatically. Open the map in your browser instead.");
    }

    document.body.removeChild(textArea);
  }
}

async function copyAndImportEventMarkdown(properties, coordinates) {
  const markdown = createObsidianMarkdown(properties, coordinates);

  try {
    await navigator.clipboard.writeText(markdown);
    setTimeout(() => {
      window.location.href = QUICK_ADD_IMPORT_URI;
    }, 300);
  } catch (error) {
    console.error(error);
    const textArea = document.createElement("textarea");
    textArea.value = markdown;
    document.body.appendChild(textArea);
    textArea.select();

    try {
      document.execCommand("copy");
      setTimeout(() => {
        window.location.href = QUICK_ADD_IMPORT_URI;
      }, 300);
    } catch (fallbackError) {
      alert("Could not copy automatically. Copy the note markdown first, then run the QuickAdd command manually.");
    }

    document.body.removeChild(textArea);
  }
}

async function loadDataset(periodKey) {
  if (state.cache.has(periodKey)) {
    return state.cache.get(periodKey);
  }

  const dataset = DATASETS[periodKey];
  if (!FIRMS_MAP_KEY) {
    throw new Error("Missing public FIRMS map key in wildfires/config.js");
  }

  const fetchedAt = new Date();
  const allFeatures = [];

  for (const sourceName of Object.keys(FIRMS_SOURCES)) {
    const url = `${FIRMS_SOURCE_URL}api/area/csv/${encodeURIComponent(FIRMS_MAP_KEY)}/${sourceName}/world/${dataset.dayRange}`;
    const response = await fetch(url, { cache: "no-store" });
    if (!response.ok) {
      throw new Error(`Could not load ${dataset.label} FIRMS data for ${sourceName} (${response.status})`);
    }

    const rows = parseCsv(await response.text());
    rows.forEach((row) => {
      const feature = rowToFeature(row, sourceName, fetchedAt);
      if (feature) allFeatures.push(feature);
    });
  }

  const data = buildLiveCollection(allFeatures, dataset.label, fetchedAt);
  state.cache.set(periodKey, data);
  return data;
}

async function refreshMapForCurrentState() {
  const requestId = ++state.activeRequestId;
  elements.lastUpdate.textContent = "loading";
  setStatusMessage("");

  try {
    const collection = await loadDataset(state.period);
    if (requestId !== state.activeRequestId) return;

    state.currentCollection = collection;
    const displayFeatures = filteredFeaturesFrom(collection);
    const displayCollection = buildDisplayCollection(
      displayFeatures,
      collection.metadata || {}
    );
    setMapData(displayCollection);
    if (!Array.isArray(collection.features) || collection.features.length === 0) {
      setStatusMessage("No wildfire detections were returned for this period.");
    }
  } catch (error) {
    console.error(error);
    state.currentCollection = buildDisplayCollection([], {
      generated_at_utc: null
    });
    setMapData(state.currentCollection);
    elements.lastUpdate.textContent = "error";
    const message = String(error && error.message ? error.message : error || "");
    if (message.includes("(404)")) {
      setStatusMessage("FIRMS returned 404. The public key in `wildfires/config.js` is likely invalid, expired, or not accepted.");
    } else if (message.includes("Missing public FIRMS map key")) {
      setStatusMessage("No public FIRMS key was found. Add one to `wildfires/config.js`.");
    } else {
      setStatusMessage("Could not load live FIRMS wildfire data. Check `wildfires/config.js`, the FIRMS key, and browser network access.");
    }
  }
}

function bindControls() {
  elements.periodSelect.addEventListener("change", (event) => {
    state.period = event.target.value;
    refreshMapForCurrentState();
  });

  elements.intensitySelect.addEventListener("change", (event) => {
    state.intensity = event.target.value;
    refreshMapForCurrentState();
  });

  elements.confidenceSelect.addEventListener("change", (event) => {
    state.confidence = event.target.value;
    refreshMapForCurrentState();
  });

  elements.satelliteSelect.addEventListener("change", (event) => {
    state.satellite = event.target.value;
    refreshMapForCurrentState();
  });
}

function attachPopupHandlers(popup, properties, coordinates) {
  const popupElement = popup.getElement();
  const obsidianButton = popupElement.querySelector("#obsidian-note-button");
  const copyMarkdownButton = popupElement.querySelector("#copy-markdown-button");
  const copyImportButton = popupElement.querySelector("#copy-import-button");

  if (obsidianButton) {
    obsidianButton.addEventListener("click", () => {
      openEventInObsidian(properties, coordinates);
    });
  }

  if (copyMarkdownButton) {
    copyMarkdownButton.addEventListener("click", () => {
      copyEventMarkdown(properties, coordinates);
    });
  }

  if (copyImportButton) {
    copyImportButton.addEventListener("click", () => {
      copyAndImportEventMarkdown(properties, coordinates);
    });
  }
}

function initialiseMapLayers() {
  map.addSource("fires", {
    type: "geojson",
    data: buildDisplayCollection([]),
    cluster: true,
    clusterRadius: 48,
    clusterMaxZoom: 7
  });

  map.addLayer({
    id: "fire-clusters",
    type: "circle",
    source: "fires",
    filter: ["has", "point_count"],
    paint: {
      "circle-color": [
        "step",
        ["get", "point_count"],
        "#ffb347",
        25,
        "#ff8a3d",
        100,
        "#ff5c39",
        300,
        "#d7263d"
      ],
      "circle-radius": [
        "step",
        ["get", "point_count"],
        16,
        25,
        22,
        100,
        30,
        300,
        38
      ],
      "circle-opacity": 0.8,
      "circle-stroke-width": 1.5,
      "circle-stroke-color": "#ffffff"
    }
  });

  map.addLayer({
    id: "fire-cluster-count",
    type: "symbol",
    source: "fires",
    filter: ["has", "point_count"],
    layout: {
      "text-field": ["get", "point_count_abbreviated"],
      "text-font": ["Open Sans Bold"],
      "text-size": 12
    },
    paint: {
      "text-color": "#ffffff"
    }
  });

  map.addLayer({
    id: "fire-glow",
    type: "circle",
    source: "fires",
    filter: ["!", ["has", "point_count"]],
    paint: {
      "circle-radius": ["*", ["get", "marker_radius"], 1.85],
      "circle-color": ["get", "marker_colour"],
      "circle-opacity": ["get", "glow_opacity"]
    }
  });

  map.addLayer({
    id: "fire-points",
    type: "circle",
    source: "fires",
    filter: ["!", ["has", "point_count"]],
    paint: {
      "circle-radius": ["get", "marker_radius"],
      "circle-color": ["get", "marker_colour"],
      "circle-opacity": ["get", "marker_opacity"],
      "circle-stroke-color": "#ffffff",
      "circle-stroke-width": 1.2
    }
  });

  map.on("click", "fire-clusters", (event) => {
    const feature = map.queryRenderedFeatures(event.point, {
      layers: ["fire-clusters"]
    })[0];
    const clusterId = feature.properties.cluster_id;

    map.getSource("fires").getClusterExpansionZoom(clusterId, (error, zoom) => {
      if (error) return;

      map.easeTo({
        center: feature.geometry.coordinates,
        zoom
      });
    });
  });

  map.on("click", "fire-points", (event) => {
    const feature = event.features[0];
    const properties = feature.properties;
    const coordinates = feature.geometry.coordinates.slice();

    const popup = new maplibregl.Popup({
      closeButton: true,
      closeOnClick: true,
      maxWidth: "340px",
      offset: 18,
      focusAfterOpen: false
    })
      .setLngLat(coordinates)
      .setHTML(buildPopupHtml(properties, coordinates))
      .addTo(map);

    attachPopupHandlers(popup, properties, coordinates);
  });

  ["fire-clusters", "fire-points"].forEach((layerId) => {
    map.on("mouseenter", layerId, () => {
      map.getCanvas().style.cursor = "pointer";
    });

    map.on("mouseleave", layerId, () => {
      map.getCanvas().style.cursor = "";
    });
  });
}

bindControls();

map.on("load", () => {
  initialiseMapLayers();
  refreshMapForCurrentState();
  setInterval(() => {
    state.cache.clear();
    refreshMapForCurrentState();
  }, 5 * 60 * 1000);
});

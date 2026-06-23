import maplibregl from "maplibre-gl";
import "maplibre-gl/dist/maplibre-gl.css";
import { useEffect, useMemo, useRef, useState } from "react";

const CATEGORY_COLORS: Record<string, string> = {
  pharmacy: "#10b981",
  clinic: "#06b6d4",
  hospital: "#8b5cf6",
  doctor: "#3b82f6",
  dentist: "#f59e0b",
  laboratory: "#ec4899",
  radiology: "#f97316",
  health_center: "#14b8a6",
  veterinary: "#84cc16",
  cafe: "#14b8a6",
  restaurant: "#f97316",
  fast_food: "#f59e0b",
  bar: "#8b5cf6",
  ice_cream: "#ec4899",
  supermarket: "#22c55e",
  clothing: "#06b6d4",
  bakery: "#f59e0b",
  sports: "#3b82f6",
  hardware: "#64748b",
  school: "#3b82f6",
  university: "#8b5cf6",
  kindergarten: "#f97316",
  fitness: "#10b981",
  hairdresser: "#ec4899",
  optician: "#06b6d4",
  beauty: "#f472b6",
  spa: "#14b8a6",
  unknown: "#6b7280",
};

const CATEGORY_LABELS: Record<string, string> = {
  pharmacy: "Pharmacies",
  clinic: "Cliniques",
  hospital: "Hôpitaux",
  doctor: "Cabinets",
  dentist: "Dentistes",
  laboratory: "Laboratoires",
  radiology: "Radiologie",
  health_center: "Centres santé",
  veterinary: "Vétérinaire",
  cafe: "Cafés",
  restaurant: "Restaurants",
  fast_food: "Fast food",
  bar: "Bars",
  ice_cream: "Glaciers",
  supermarket: "Supermarchés",
  clothing: "Habillement",
  bakery: "Boulangeries",
  sports: "Sport",
  hardware: "Quincailleries",
  school: "Écoles",
  university: "Universités",
  kindergarten: "Crèches",
  fitness: "Fitness",
  hairdresser: "Coiffeurs",
  optician: "Opticiens",
  beauty: "Beauté",
  spa: "Spa",
  unknown: "Non classé",
};

const SECTOR_LABELS: Record<string, string> = {
  food: "Restauration",
  retail: "Commerce de détail",
  education: "Éducation",
  wellness: "Bien-être & beauté",
};

const SECTOR_COLORS: Record<string, string> = {
  food: "#f97316",
  retail: "#22c55e",
  education: "#3b82f6",
  wellness: "#ec4899",
};

const SECTOR_OPTIONS = [
  { key: "medical", label: "Santé" },
  { key: "food", label: "Restauration" },
  { key: "retail", label: "Commerce" },
  { key: "education", label: "Éducation" },
  { key: "wellness", label: "Bien-être" },
];

const INVESTMENT_CATEGORY_TO_MAP: Record<string, string> = {
  Pharmacy: "pharmacy",
  "Medical Analysis Laboratory": "laboratory",
  "Radiology Center": "radiology",
  "Dental Clinic": "dentist",
  "Veterinary Clinic": "veterinary",
  "General Doctor Cabinet": "doctor",
  "Pediatric Cabinet": "doctor",
  "Dermatology Cabinet": "doctor",
  "Physiotherapy Center": "health_center",
  "Small Private Clinic": "clinic",
  "Emergency Care Center": "hospital",
};

function categoryColor(cat: string): string {
  const lower = cat.toLowerCase();
  for (const [key, color] of Object.entries(CATEGORY_COLORS)) {
    if (lower.includes(key)) return color;
  }
  return CATEGORY_COLORS.unknown;
}

function categoryLabel(cat: string): string {
  return CATEGORY_LABELS[cat] || cat;
}

function mapCategoryFromAnswer(answer: any): string | null {
  if (answer?.subcategory && CATEGORY_LABELS[answer.subcategory]) return answer.subcategory;
  const category = answer?.category;
  if (!category) return null;
  if (SECTOR_LABELS[category]) return null;
  if (INVESTMENT_CATEGORY_TO_MAP[category]) return INVESTMENT_CATEGORY_TO_MAP[category];
  if (CATEGORY_LABELS[category]) return category;
  return null;
}

function mapSectorFromAnswer(answer: any): string | null {
  if (answer?.sector && SECTOR_LABELS[answer.sector]) return answer.sector;
  const category = answer?.category;
  if (category && SECTOR_LABELS[category]) return category;
  return null;
}

function findKpi(answer: any, label: string): string | undefined {
  const normalized = label.toLowerCase();
  return answer?.kpis?.find((item: any) => item.label?.toLowerCase().includes(normalized))?.value;
}

function geometryBounds(geometry: any): [[number, number], [number, number]] | null {
  const coordinates: number[][] = [];
  const collect = (value: any) => {
    if (
      Array.isArray(value) &&
      value.length >= 2 &&
      typeof value[0] === "number" &&
      typeof value[1] === "number"
    ) {
      coordinates.push([value[0], value[1]]);
      return;
    }
    if (Array.isArray(value)) value.forEach(collect);
  };
  collect(geometry?.coordinates);
  if (!coordinates.length) return null;
  const longitudes = coordinates.map(([lon]) => lon);
  const latitudes = coordinates.map(([, lat]) => lat);
  return [
    [Math.min(...longitudes), Math.min(...latitudes)],
    [Math.max(...longitudes), Math.max(...latitudes)],
  ];
}

function pointInRing(point: number[], ring: number[][]): boolean {
  const [x, y] = point;
  let inside = false;
  for (let i = 0, j = ring.length - 1; i < ring.length; j = i++) {
    const [xi, yi] = ring[i];
    const [xj, yj] = ring[j];
    const crosses = yi > y !== yj > y;
    if (crosses && x < ((xj - xi) * (y - yi)) / (yj - yi) + xi) inside = !inside;
  }
  return inside;
}

function pointInPolygon(point: number[], polygon: number[][][]): boolean {
  if (!polygon.length || !pointInRing(point, polygon[0])) return false;
  return !polygon.slice(1).some((hole) => pointInRing(point, hole));
}

function pointInGeometry(point: number[], geometry: any): boolean {
  if (geometry?.type === "Polygon") return pointInPolygon(point, geometry.coordinates);
  if (geometry?.type === "MultiPolygon") {
    return geometry.coordinates.some((polygon: number[][][]) => pointInPolygon(point, polygon));
  }
  return false;
}

function normalizeZoneName(value: string | undefined): string {
  return (value ?? "")
    .normalize("NFD")
    .replace(/[\u0300-\u036f]/g, "")
    .replace(/[’`]/g, "'")
    .replace(/[^a-zA-Z0-9]+/g, "")
    .toLowerCase();
}

function findZoneFeature(boundaryData: any, zone: string): any | undefined {
  const normalizedZone = normalizeZoneName(zone);
  return (boundaryData.features ?? []).find(
    (feature: any) => normalizeZoneName(feature.properties?.zone) === normalizedZone,
  );
}

function filterFacilitiesForZone(
  data: any,
  boundaryData: any,
  category: string | null,
  zone: string,
): any {
  const zoneFeature = findZoneFeature(boundaryData, zone);
  const normalizedZone = normalizeZoneName(zone);
  return {
    ...data,
    features: (data.features ?? []).filter((feature: any) => {
      const matchesCategory =
        !category || (feature.properties?.category ?? "unknown") === category;
      if (!matchesCategory) return false;
      if (!normalizedZone) return true;

      const district = normalizeZoneName(feature.properties?.district);
      if (district && district === normalizedZone) return true;

      if (!zoneFeature || feature.geometry?.type !== "Point") return true;
      return pointInGeometry(feature.geometry.coordinates, zoneFeature.geometry);
    }),
  };
}

function sectorPointsToGeojson(points: any[], sector: string): any {
  return {
    type: "FeatureCollection",
    features: points
      .filter((point) => Number.isFinite(Number(point.lat)) && Number.isFinite(Number(point.lon)))
      .map((point) => {
        const category = point.category ?? "unknown";
        return {
          type: "Feature",
          geometry: {
            type: "Point",
            coordinates: [Number(point.lon), Number(point.lat)],
          },
          properties: {
            id: point.id,
            name: point.name || "Sans nom",
            sector,
            category,
            district: point.district || "Unknown",
            confidence_score: point.confidence,
            source_url: point.source_url,
            _color: categoryColor(category),
          },
        };
      }),
  };
}

function legendItemsFromFeatures(features: any[] = []): { cat: string; color: string; count: number }[] {
  const counts: Record<string, number> = {};
  for (const feature of features) {
    const cat = feature.properties?.category ?? "unknown";
    counts[cat] = (counts[cat] ?? 0) + 1;
  }

  return Object.entries(counts)
    .sort((a, b) => b[1] - a[1])
    .map(([cat, count]) => ({ cat, color: categoryColor(cat), count }));
}

function decorateFacilityGeojson(data: any): any {
  for (const feature of data.features ?? []) {
    const cat = feature.properties?.category ?? "unknown";
    const color = categoryColor(cat);
    feature.properties = { ...feature.properties, _color: color };
  }

  return data;
}

type Props = {
  focusLabel?: string;
  focusLat?: number;
  focusLon?: number;
  focusZoom?: number;
  answer?: any;
};

type SelectedFacility = {
  name: string;
  category: string;
  district: string;
  confidence?: number;
  source_url?: string;
};

export function InvestMap({ focusLabel, focusLat, focusLon, focusZoom, answer }: Props) {
  const resolvedLabel = focusLabel ?? answer?.answer?.neighborhood ?? answer?.top_zone ?? "Casablanca";
  const resolvedLat = focusLat ?? answer?.map_focus?.lat ?? 33.57;
  const resolvedLon = focusLon ?? answer?.map_focus?.lon ?? -7.59;
  const resolvedZoom = focusZoom ?? answer?.map_focus?.zoom ?? 12;
  const topOpportunity =
    answer?.related_opportunities?.find((item: any) => item.zone === answer?.top_zone) ||
    answer?.related_opportunities?.[0];
  const contextMetrics = [
    { label: "Score", value: topOpportunity?.score ? `${topOpportunity.score}%` : findKpi(answer, "score") },
    { label: "Population", value: findKpi(answer, "population") },
    { label: "Supply gap", value: findKpi(answer, "supply gap") },
    { label: "Risque", value: findKpi(answer, "risque") },
  ].filter((item) => item.value);
  const containerRef = useRef<HTMLDivElement>(null);
  const mapRef = useRef<maplibregl.Map | null>(null);
  const [geojson, setGeojson] = useState<any>({ type: "FeatureCollection", features: [] });
  const [boundaries, setBoundaries] = useState<any>({ type: "FeatureCollection", features: [] });
  const [selected, setSelected] = useState<SelectedFacility | null>(null);
  const [loading, setLoading] = useState(true);
  const answerSector = mapSectorFromAnswer(answer);
  const answerSubcategory = answer?.subcategory && CATEGORY_LABELS[answer.subcategory]
    ? answer.subcategory
    : null;
  const [manualSector, setManualSector] = useState<string | null>(null);
  const selectedSector = manualSector ?? answerSector;
  const selectedCategory = manualSector
    ? null
    : answerSubcategory || (selectedSector ? null : mapCategoryFromAnswer(answer));
  const selectedDomainLabel = selectedCategory
    ? categoryLabel(selectedCategory)
    : selectedSector
      ? SECTOR_LABELS[selectedSector]
      : "Santé";
  const selectedDomainColor = selectedCategory
    ? categoryColor(selectedCategory)
    : selectedSector
      ? SECTOR_COLORS[selectedSector]
      : CATEGORY_COLORS.pharmacy;

  const filteredGeojson = useMemo(() => {
    return filterFacilitiesForZone(geojson, boundaries, selectedCategory, resolvedLabel);
  }, [geojson, boundaries, selectedCategory, resolvedLabel]);
  const domainFacilityCount = filteredGeojson.features?.length ?? 0;
  const filteredLegendItems = useMemo(
    () => legendItemsFromFeatures(filteredGeojson.features ?? []),
    [filteredGeojson],
  );

  useEffect(() => {
    setManualSector(null);
  }, [answer?.question, answer?.category, answer?.subcategory, answer?.top_zone]);

  useEffect(() => {
    if (!containerRef.current || mapRef.current) return;

    const map = new maplibregl.Map({
      container: containerRef.current,
      style: {
        version: 8,
        sources: {
          "carto-dark": {
            type: "raster",
            tiles: [
              "https://a.basemaps.cartocdn.com/dark_all/{z}/{x}/{y}@2x.png",
              "https://b.basemaps.cartocdn.com/dark_all/{z}/{x}/{y}@2x.png",
              "https://c.basemaps.cartocdn.com/dark_all/{z}/{x}/{y}@2x.png",
            ],
            tileSize: 256,
            attribution:
              '&copy; <a href="https://carto.com/">CARTO</a> &copy; <a href="https://www.openstreetmap.org/copyright">OSM</a>',
          },
        },
        layers: [
          {
            id: "carto-dark-layer",
            type: "raster",
            source: "carto-dark",
            minzoom: 0,
            maxzoom: 19,
          },
        ],
      },
      center: [resolvedLon, resolvedLat],
      zoom: resolvedZoom,
    });

    map.addControl(new maplibregl.NavigationControl(), "top-right");
    mapRef.current = map;

    map.on("load", async () => {
      try {
        const boundaryResponse = await fetch("/api/zone-boundaries");
        const boundaryData = boundaryResponse.ok
          ? await boundaryResponse.json()
          : { type: "FeatureCollection", features: [] };

        setBoundaries(boundaryData);

        const initialZoneFeature = findZoneFeature(boundaryData, resolvedLabel);
        map.addSource("suggested-zone", {
          type: "geojson",
          data: {
            type: "FeatureCollection",
            features: initialZoneFeature ? [initialZoneFeature] : [],
          },
        });
        map.addLayer({
          id: "suggested-zone-fill",
          type: "fill",
          source: "suggested-zone",
          paint: {
            "fill-color": "#f59e0b",
            "fill-opacity": 0.42,
          },
        });
        map.addLayer({
          id: "suggested-zone-glow",
          type: "line",
          source: "suggested-zone",
          paint: {
            "line-color": "#fbbf24",
            "line-width": 10,
            "line-blur": 5,
            "line-opacity": 0.5,
          },
        });
        map.addLayer({
          id: "suggested-zone-outline",
          type: "line",
          source: "suggested-zone",
          paint: {
            "line-color": "#fde68a",
            "line-width": 4,
            "line-opacity": 1,
          },
        });

        map.addSource("facilities", {
          type: "geojson",
          data: { type: "FeatureCollection", features: [] },
        });

        map.addLayer({
          id: "facilities-points",
          type: "circle",
          source: "facilities",
          minzoom: 8,
          paint: {
            "circle-radius": ["interpolate", ["linear"], ["zoom"], 8, 3, 16, 8],
            "circle-color": ["get", "_color"],
            "circle-stroke-width": 1.5,
            "circle-stroke-color": "rgba(255,255,255,0.82)",
            "circle-opacity": 0.92,
          },
        });
        map.addLayer({
          id: "suggested-zone-label",
          type: "symbol",
          source: "suggested-zone",
          layout: {
            "text-field": ["get", "zone"],
            "text-size": 18,
            "text-anchor": "center",
            "text-allow-overlap": true,
          },
          paint: {
            "text-color": "#fff7ed",
            "text-halo-color": "#78350f",
            "text-halo-width": 2,
            "text-halo-blur": 1,
          },
        });

        const initialBounds = initialZoneFeature
          ? geometryBounds(initialZoneFeature.geometry)
          : null;
        if (initialBounds) {
          map.fitBounds(initialBounds, { padding: 80, duration: 0, maxZoom: 13 });
        }

        map.on("click", "facilities-points", (e) => {
          const feature = e.features?.[0];
          if (!feature || !feature.geometry || feature.geometry.type !== "Point") return;
          const props = feature.properties ?? {};
          const coords = (feature.geometry as GeoJSON.Point).coordinates as [number, number];
          const facility = {
            name: props.name || props.name_fr || "Sans nom",
            category: props.category ?? "unknown",
            district: props.district ?? "Unknown",
            confidence: props.confidence_score ? Number(props.confidence_score) : undefined,
            source_url: props.source_url,
          };
          setSelected(facility);
          const popupContent = document.createElement("div");
          const popupName = document.createElement("strong");
          popupName.textContent = facility.name;
          const popupCategory = document.createElement("span");
          popupCategory.style.color = "#10b981";
          popupCategory.textContent = categoryLabel(facility.category);
          popupContent.append(
            popupName,
            document.createElement("br"),
            popupCategory,
            document.createElement("br"),
            document.createTextNode(facility.district),
          );
          new maplibregl.Popup({ offset: 10, className: "invest-popup" })
            .setLngLat(coords)
            .setDOMContent(popupContent)
            .addTo(map);
        });

        map.on("mouseenter", "facilities-points", () => {
          map.getCanvas().style.cursor = "pointer";
        });
        map.on("mouseleave", "facilities-points", () => {
          map.getCanvas().style.cursor = "";
        });
        requestAnimationFrame(() => map.resize());
      } finally {
        requestAnimationFrame(() => map.resize());
      }
    });

    return () => {
      map.remove();
      mapRef.current = null;
    };
  }, []);

  useEffect(() => {
    let cancelled = false;

    async function loadFacilities() {
      setLoading(true);
      try {
        const subcategoryParam = selectedCategory
          ? `&subcategory=${encodeURIComponent(selectedCategory)}`
          : "";
        const response = selectedSector
          ? await fetch(`/api/sector-facilities?sector=${encodeURIComponent(selectedSector)}${subcategoryParam}&limit=2000`)
          : await fetch("/api/geojson");
        if (!response.ok) return;
        const rawData = selectedSector
          ? sectorPointsToGeojson(await response.json(), selectedSector)
          : await response.json();
        const decorated = decorateFacilityGeojson(rawData);
        if (cancelled) return;
        setGeojson(decorated);
        setSelected(null);
      } finally {
        if (!cancelled) setLoading(false);
      }
    }

    loadFacilities();

    return () => {
      cancelled = true;
    };
  }, [selectedSector, selectedCategory]);

  useEffect(() => {
    const source = mapRef.current?.getSource("facilities") as maplibregl.GeoJSONSource | undefined;
    if (!source) return;
    source.setData(filteredGeojson);
  }, [filteredGeojson]);

  useEffect(() => {
    if (!mapRef.current) return;
    const map = mapRef.current;
    const zoneFeature = findZoneFeature(boundaries, resolvedLabel);
    const zoneData = zoneFeature
      ? { type: "FeatureCollection" as const, features: [zoneFeature] }
      : { type: "FeatureCollection" as const, features: [] };

    const updateZone = () => {
      const source = map.getSource("suggested-zone") as maplibregl.GeoJSONSource | undefined;
      if (!source) return;
      source.setData(zoneData);

      const bounds = zoneFeature ? geometryBounds(zoneFeature.geometry) : null;
      if (bounds) {
        map.fitBounds(bounds, { padding: 80, duration: 1200, maxZoom: 13 });
      } else {
        map.flyTo({ center: [resolvedLon, resolvedLat], zoom: resolvedZoom, duration: 1200 });
      }
    };

    if (map.isStyleLoaded()) updateZone();
    else map.once("load", updateZone);
  }, [boundaries, resolvedLabel, resolvedLat, resolvedLon, resolvedZoom]);

  const selectedLegend = selectedCategory
    ? filteredLegendItems.find((item) => item.cat === selectedCategory)
    : null;

  return (
    <div className="invest-map-root">
      <div ref={containerRef} className="invest-map-canvas" />

      <div className="map-intelligence-panel">
        <div className="map-panel-header">
          <span>Invest Map</span>
          <strong>{resolvedLabel}</strong>
        </div>
        <div className="map-stat-grid">
          <div>
            <span>Domaine</span>
            <strong>{selectedDomainLabel}</strong>
          </div>
          <div>
            <span>Points affichés</span>
            <strong>{domainFacilityCount}</strong>
          </div>
          <div>
            <span>Zone suggérée</span>
            <strong>{resolvedLabel}</strong>
          </div>
        </div>
        {contextMetrics.length ? (
          <div className="map-context-row">
            {contextMetrics.map((item) => (
              <div key={item.label}>
                <span>{item.label}</span>
                <strong>{item.value}</strong>
              </div>
            ))}
          </div>
        ) : null}
        <div className="map-source-note">
          {loading
            ? "Chargement des données OSM..."
            : selectedSector
              ? "Source: OpenStreetMap multi-sectoriel + pipeline Invest Search"
              : "Source: OpenStreetMap + pipeline Invest Search"}
        </div>
        <div className="map-sector-switcher" aria-label="Changer le secteur affiché">
          {SECTOR_OPTIONS.map((option) => {
            const active = option.key === "medical" ? !selectedSector : selectedSector === option.key;
            return (
              <button
                key={option.key}
                type="button"
                className={active ? "active" : ""}
                onClick={() => setManualSector(option.key === "medical" ? null : option.key)}
              >
                {option.label}
              </button>
            );
          })}
        </div>
      </div>

      {(selectedSector || selectedCategory) && (
        <div className="map-filter-panel">
          <div className="map-filter-title">
            <span>Domaine analysé</span>
          </div>
          <div className="map-filter-list">
            <div className="map-domain-chip">
              <span
                className="legend-dot"
                style={{ background: selectedDomainColor }}
              />
              <span>{selectedDomainLabel}</span>
              <strong>{selectedCategory ? (selectedLegend?.count ?? domainFacilityCount) : domainFacilityCount} recensés</strong>
            </div>
            {selectedSector && !selectedCategory
              ? filteredLegendItems.slice(0, 5).map((item) => (
                  <div className="map-domain-chip secondary" key={item.cat}>
                    <span className="legend-dot" style={{ background: item.color }} />
                    <span>{categoryLabel(item.cat)}</span>
                    <strong>{item.count}</strong>
                  </div>
                ))
              : null}
          </div>
        </div>
      )}

      {selected ? (
        <div className="map-selection-card">
          <span>Établissement sélectionné</span>
          <strong>{selected.name}</strong>
          <p>{categoryLabel(selected.category)} · {selected.district}</p>
          {selected.confidence !== undefined ? (
            <small>Confiance source: {Math.round(selected.confidence * 100)}%</small>
          ) : null}
          {selected.source_url ? (
            <a href={selected.source_url} target="_blank" rel="noreferrer">
              Voir dans OpenStreetMap
            </a>
          ) : null}
        </div>
      ) : null}
    </div>
  );
}

export default InvestMap;

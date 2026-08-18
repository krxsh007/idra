import React, { useEffect, useRef } from 'react';
import maplibregl, { Map as MapLibreMap, Marker, Popup } from 'maplibre-gl';
import { DisasterEvent, HazardZone, IncidentReport } from '../../types/api';
import { useMapStore } from '../../stores/mapStore';

interface MapContainerProps {
  activeEvent: DisasterEvent | null;
  hazardZones?: HazardZone[];
  reports?: IncidentReport[];
  onMapClick?: (coords: { lon: number; lat: number }) => void;
  isPickingLocation?: boolean;
}

const CHENNAI_BBOX_GEOJSON = {
  type: 'Feature' as const,
  properties: { name: 'Chennai Core Study Area' },
  geometry: {
    type: 'Polygon' as const,
    coordinates: [
      [
        [80.15, 12.95],
        [80.30, 12.95],
        [80.30, 13.15],
        [80.15, 13.15],
        [80.15, 12.95],
      ],
    ],
  },
};

export const MapContainer: React.FC<MapContainerProps> = ({
  activeEvent,
  hazardZones = [],
  reports = [],
  onMapClick,
  isPickingLocation = false,
}) => {
  const mapContainerRef = useRef<HTMLDivElement>(null);
  const mapRef = useRef<MapLibreMap | null>(null);
  const epicenterMarkerRef = useRef<Marker | null>(null);
  const reportMarkersRef = useRef<Marker[]>([]);

  const { center, zoom, showBBox, showHazards, showReports } = useMapStore();

  // Initialize Map
  useEffect(() => {
    if (!mapContainerRef.current || mapRef.current) return;

    const map = new maplibregl.Map({
      container: mapContainerRef.current,
      style: {
        version: 8,
        sources: {
          carto_dark: {
            type: 'raster',
            tiles: [
              'https://cartodb-basemaps-a.global.ssl.fastly.net/dark_all/{z}/{x}/{y}.png',
              'https://cartodb-basemaps-b.global.ssl.fastly.net/dark_all/{z}/{x}/{y}.png',
              'https://cartodb-basemaps-c.global.ssl.fastly.net/dark_all/{z}/{x}/{y}.png',
            ],
            tileSize: 256,
            attribution: '&copy; OpenStreetMap &copy; CARTO',
          },
        },
        layers: [
          {
            id: 'carto-dark-layer',
            type: 'raster',
            source: 'carto_dark',
            minzoom: 0,
            maxzoom: 19,
          },
        ],
      },
      center: center,
      zoom: zoom,
    });

    map.addControl(new maplibregl.NavigationControl({ showCompass: true }), 'top-right');
    map.addControl(new maplibregl.ScaleControl({ maxWidth: 100, unit: 'metric' }), 'bottom-left');

    map.on('load', () => {
      // 1. Add Study Area BBox Source & Layers
      map.addSource('study-area-bbox', {
        type: 'geojson',
        data: CHENNAI_BBOX_GEOJSON,
      });

      map.addLayer({
        id: 'study-area-bbox-fill',
        type: 'fill',
        source: 'study-area-bbox',
        paint: {
          'fill-color': '#3b82f6',
          'fill-opacity': 0.05,
        },
      });

      map.addLayer({
        id: 'study-area-bbox-line',
        type: 'line',
        source: 'study-area-bbox',
        paint: {
          'line-color': '#60a5fa',
          'line-width': 2,
          'line-dasharray': [2, 2],
        },
      });

      // 2. Add Hazard Zones Source & Layers
      map.addSource('hazard-zones-src', {
        type: 'geojson',
        data: {
          type: 'FeatureCollection',
          features: [],
        },
      });

      map.addLayer({
        id: 'hazard-zones-fill',
        type: 'fill',
        source: 'hazard-zones-src',
        paint: {
          'fill-color': [
            'match',
            ['get', 'severity'],
            'SEVERE',
            '#ef4444',
            'HIGH',
            '#f97316',
            'MODERATE',
            '#eab308',
            'LOW',
            '#06b6d4',
            '#94a3b8',
          ],
          'fill-opacity': 0.35,
        },
      });

      map.addLayer({
        id: 'hazard-zones-line',
        type: 'line',
        source: 'hazard-zones-src',
        paint: {
          'line-color': [
            'match',
            ['get', 'severity'],
            'SEVERE',
            '#dc2626',
            'HIGH',
            '#ea580c',
            'MODERATE',
            '#ca8a04',
            'LOW',
            '#0891b2',
            '#64748b',
          ],
          'line-width': 2,
        },
      });

      // Interactive popup on clicking hazard zones
      map.on('click', 'hazard-zones-fill', (e) => {
        if (!e.features || !e.features[0]) return;
        const props = e.features[0].properties;
        new Popup({ closeButton: true, className: 'idra-map-popup' })
          .setLngLat(e.lngLat)
          .setHTML(
            `<div class="p-2 text-xs font-sans">
              <div class="font-bold text-sm text-slate-900">${props?.label || 'Hazard Zone'}</div>
              <div class="mt-1 text-slate-700">Type: <span class="font-semibold">${props?.hazard_type}</span></div>
              <div class="text-slate-700">Severity: <span class="font-bold text-red-600">${props?.severity}</span></div>
              ${props?.is_impassable ? '<div class="mt-1 text-red-700 font-bold">⛔ Road Impassable</div>' : ''}
            </div>`
          )
          .addTo(map);
      });

      map.on('mouseenter', 'hazard-zones-fill', () => {
        map.getCanvas().style.cursor = 'pointer';
      });
      map.on('mouseleave', 'hazard-zones-fill', () => {
        map.getCanvas().style.cursor = '';
      });
    });

    mapRef.current = map;

    return () => {
      map.remove();
      mapRef.current = null;
    };
  }, []);

  // Handle map click for coordinate picking
  useEffect(() => {
    const map = mapRef.current;
    if (!map) return;

    const handleClick = (e: maplibregl.MapMouseEvent) => {
      if (onMapClick) {
        onMapClick({ lon: e.lngLat.lng, lat: e.lngLat.lat });
      }
    };

    map.on('click', handleClick);
    return () => {
      map.off('click', handleClick);
    };
  }, [onMapClick]);

  // Cursor style when picking location
  useEffect(() => {
    const map = mapRef.current;
    if (!map) return;
    map.getCanvas().style.cursor = isPickingLocation ? 'crosshair' : '';
  }, [isPickingLocation]);

  // Update Hazard Zones GeoJSON data
  useEffect(() => {
    const map = mapRef.current;
    if (!map || !map.isStyleLoaded()) return;

    const source = map.getSource('hazard-zones-src') as maplibregl.GeoJSONSource | undefined;
    if (source) {
      source.setData({
        type: 'FeatureCollection',
        features: hazardZones.map((z) => ({
          type: 'Feature',
          properties: {
            id: z.id,
            label: z.label,
            hazard_type: z.hazard_type,
            severity: z.severity,
            is_impassable: z.is_impassable,
          },
          geometry: z.geometry,
        })),
      });
    }
  }, [hazardZones]);

  // Update Active Event Epicenter Marker with Pulsing Animation
  useEffect(() => {
    const map = mapRef.current;
    if (!map) return;

    if (epicenterMarkerRef.current) {
      epicenterMarkerRef.current.remove();
      epicenterMarkerRef.current = null;
    }

    if (activeEvent) {
      const el = document.createElement('div');
      el.className = 'epicenter-pulse';
      const dot = document.createElement('div');
      dot.className = 'epicenter-dot';
      el.appendChild(dot);

      const popup = new Popup({ offset: 25, closeButton: false }).setHTML(
        `<div class="p-2 text-xs font-sans">
          <div class="font-bold text-slate-900">${activeEvent.name}</div>
          <div class="text-slate-600">${activeEvent.disaster_type} &bull; Radius: ${activeEvent.radius_m}m</div>
        </div>`
      );

      const marker = new Marker({ element: el })
        .setLngLat([activeEvent.epicenter.lon, activeEvent.epicenter.lat])
        .setPopup(popup)
        .addTo(map);

      epicenterMarkerRef.current = marker;

      // Pan to event epicenter
      map.easeTo({
        center: [activeEvent.epicenter.lon, activeEvent.epicenter.lat],
        zoom: 12,
        duration: 1000,
      });
    }
  }, [activeEvent]);

  // Update Report Markers
  useEffect(() => {
    const map = mapRef.current;
    if (!map) return;

    reportMarkersRef.current.forEach((m) => m.remove());
    reportMarkersRef.current = [];

    if (showReports) {
      reports.forEach((rep) => {
        const el = document.createElement('div');
        el.className = 'w-4 h-4 rounded-full border-2 border-white shadow-md flex items-center justify-center cursor-pointer';
        el.style.backgroundColor = rep.casualties_reported ? '#dc2626' : '#f59e0b';

        const popup = new Popup({ offset: 15 }).setHTML(
          `<div class="p-2 text-xs font-sans max-w-xs">
            <div class="font-bold text-slate-900">${rep.source} Report</div>
            <div class="mt-1 text-slate-700 line-clamp-3">${rep.body}</div>
            ${rep.casualties_reported ? '<div class="mt-1 text-red-600 font-bold">⚠️ Casualties Reported</div>' : ''}
            ${rep.people_affected ? `<div class="text-slate-600">Affected: ${rep.people_affected} people</div>` : ''}
          </div>`
        );

        const marker = new Marker({ element: el })
          .setLngLat([rep.location.lon, rep.location.lat])
          .setPopup(popup)
          .addTo(map);

        reportMarkersRef.current.push(marker);
      });
    }
  }, [reports, showReports]);

  // Toggle Layer Visibilities
  useEffect(() => {
    const map = mapRef.current;
    if (!map || !map.isStyleLoaded()) return;

    if (map.getLayer('study-area-bbox-fill') && map.getLayer('study-area-bbox-line')) {
      const visibility = showBBox ? 'visible' : 'none';
      map.setLayoutProperty('study-area-bbox-fill', 'visibility', visibility);
      map.setLayoutProperty('study-area-bbox-line', 'visibility', visibility);
    }

    if (map.getLayer('hazard-zones-fill') && map.getLayer('hazard-zones-line')) {
      const visibility = showHazards ? 'visible' : 'none';
      map.setLayoutProperty('hazard-zones-fill', 'visibility', visibility);
      map.setLayoutProperty('hazard-zones-line', 'visibility', visibility);
    }
  }, [showBBox, showHazards]);

  return (
    <div className="relative w-full h-full min-h-[500px] rounded-xl overflow-hidden border border-slate-800 shadow-inner">
      <div ref={mapContainerRef} className="w-full h-full" />
      {isPickingLocation && (
        <div className="absolute top-4 left-1/2 -translate-x-1/2 bg-blue-600/90 text-white text-xs px-3 py-1.5 rounded-full shadow-lg border border-blue-400/40 backdrop-blur-sm animate-bounce">
          Click anywhere on the map to set location
        </div>
      )}
    </div>
  );
};

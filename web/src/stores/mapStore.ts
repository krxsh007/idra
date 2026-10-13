import { create } from 'zustand';

interface MapState {
  center: [number, number];
  zoom: number;
  showBBox: boolean;
  showHazards: boolean;
  showReports: boolean;
  showFacilities: boolean;
  showRoutes: boolean;
  selectedMarker: { type: 'event' | 'hazard' | 'report'; id: string; } | null;
  setViewport: (center: [number, number], zoom: number) => void;
  toggleLayer: (layer: 'showBBox' | 'showHazards' | 'showReports' | 'showFacilities' | 'showRoutes') => void;
  setSelectedMarker: (marker: { type: 'event' | 'hazard' | 'report'; id: string; } | null) => void;
  resetView: () => void;
}

const CHENNAI_CENTER: [number, number] = [80.225, 13.05];
const DEFAULT_ZOOM = 11.5;

export const useMapStore = create<MapState>((set) => ({
  center: CHENNAI_CENTER,
  zoom: DEFAULT_ZOOM,
  showBBox: true,
  showHazards: true,
  showReports: true,
  showFacilities: true,
  showRoutes: true,
  selectedMarker: null,

  setViewport: (center: [number, number], zoom: number) => {
    set({ center, zoom });
  },

  toggleLayer: (layer: 'showBBox' | 'showHazards' | 'showReports' | 'showFacilities' | 'showRoutes') => {
    set((state) => ({ [layer]: !state[layer] }));
  },

  setSelectedMarker: (marker) => {
    set({ selectedMarker: marker });
  },

  resetView: () => {
    set({ center: CHENNAI_CENTER, zoom: DEFAULT_ZOOM });
  },
}));

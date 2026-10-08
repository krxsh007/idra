import React, { useEffect, useState } from 'react';
import { QueryClient, QueryClientProvider, useQuery } from '@tanstack/react-query';
import { ClipboardList, FileText } from 'lucide-react';
import { Header } from './components/layout/Header';
import { MapContainer } from './components/map/MapContainer';
import { LayerControls } from './components/map/LayerControls';
import { EventDetailPanel } from './components/events/EventDetailPanel';
import { BriefingPanel } from './components/briefing/BriefingPanel';
import { RunTimeline } from './components/runs/RunTimeline';
import { CitizenChatDrawer } from './components/assistant/CitizenChatDrawer';
import { LoginModal } from './components/auth/LoginModal';
import { EventCreateModal } from './components/events/EventCreateModal';
import { HazardZoneCreateModal } from './components/hazards/HazardZoneCreateModal';
import { ReportSubmissionModal } from './components/reports/ReportSubmissionModal';
import { useAuthStore } from './stores/authStore';
import { useEventStore } from './stores/eventStore';
import { api } from './lib/api';
import { EpicenterPoint } from './types/api';

const queryClient = new QueryClient({
  defaultOptions: {
    queries: {
      refetchOnWindowFocus: false,
      staleTime: 5000,
    },
  },
});

const Dashboard: React.FC = () => {
  const { checkAuth } = useAuthStore();
  const { selectedEvent, setActiveEvent } = useEventStore();

  // Modals state
  const [isLoginOpen, setIsLoginOpen] = useState(false);
  const [isNewEventOpen, setIsNewEventOpen] = useState(false);
  const [isNewHazardOpen, setIsNewHazardOpen] = useState(false);
  const [isSubmitReportOpen, setIsSubmitReportOpen] = useState(false);

  // Map location picker state
  const [isPickingLocation, setIsPickingLocation] = useState(false);
  const [onPickCallback, setOnPickCallback] = useState<((coords: EpicenterPoint) => void) | null>(null);

  // Operations tab and map focus state
  const [sidebarTab, setSidebarTab] = useState<'briefing' | 'details'>('briefing');
  const [focusCoordinates, setFocusCoordinates] = useState<{ lon: number; lat: number } | null>(null);

  useEffect(() => {
    checkAuth();
  }, [checkAuth]);

  // Fetch all events
  const { data: eventsData, refetch: refetchEvents } = useQuery({
    queryKey: ['events'],
    queryFn: () => api.getEvents(),
  });

  // Automatically select first event if none selected
  useEffect(() => {
    if (!selectedEvent && eventsData?.items && eventsData.items.length > 0) {
      setActiveEvent(eventsData.items[0]);
    }
  }, [selectedEvent, eventsData, setActiveEvent]);

  // Fetch hazard zones for selected event
  const { data: hazardZonesData, refetch: refetchHazards } = useQuery({
    queryKey: ['hazardZones', selectedEvent?.id],
    queryFn: () => (selectedEvent ? api.getEventHazardZones(selectedEvent.id) : { items: [], total: 0 }),
    enabled: !!selectedEvent?.id,
  });

  // Fetch reports for selected event
  const { data: reportsData, refetch: refetchReports } = useQuery({
    queryKey: ['reports', selectedEvent?.id],
    queryFn: () => (selectedEvent ? api.getEventReports(selectedEvent.id) : { items: [], total: 0, limit: 20, offset: 0 }),
    enabled: !!selectedEvent?.id,
  });

  // Fetch facilities for map display
  const { data: facilitiesData } = useQuery({
    queryKey: ['facilities'],
    queryFn: () => api.getFacilities(),
  });

  const handleStartLocationPick = (callback: (coords: EpicenterPoint) => void) => {
    setOnPickCallback(() => callback);
    setIsPickingLocation(true);
  };

  const handleMapClick = (coords: { lon: number; lat: number }) => {
    if (isPickingLocation && onPickCallback) {
      onPickCallback(coords);
      setIsPickingLocation(false);
      setOnPickCallback(null);
    }
  };

  return (
    <div className="flex flex-col h-screen w-screen overflow-hidden bg-slate-950 text-slate-100">
      {/* Top Header */}
      <Header
        events={eventsData?.items || []}
        activeEvent={selectedEvent}
        onSelectEvent={setActiveEvent}
        onOpenLogin={() => setIsLoginOpen(true)}
        onOpenNewEvent={() => setIsNewEventOpen(true)}
        onOpenSubmitReport={() => setIsSubmitReportOpen(true)}
      />

      {/* Main Map + Sidebar Workspace */}
      <div className="flex-1 flex overflow-hidden relative">
        {/* Geospatial Map Area */}
        <main className="flex-1 relative h-full">
          {isPickingLocation && (
            <div className="absolute top-4 left-1/2 -translate-x-1/2 z-20 bg-blue-600/95 text-white text-xs font-medium px-4 py-2 rounded-full shadow-xl border border-blue-400/50 flex items-center gap-3">
              <span>Click anywhere inside the dashed blue Chennai study area box to select coordinates</span>
              <button
                type="button"
                onClick={() => {
                  setIsPickingLocation(false);
                  setOnPickCallback(null);
                }}
                className="underline hover:text-blue-200"
              >
                Cancel
              </button>
            </div>
          )}
          <MapContainer
            activeEvent={selectedEvent}
            hazardZones={hazardZonesData?.items || []}
            reports={reportsData?.items || []}
            facilities={facilitiesData?.items || []}
            onMapClick={handleMapClick}
            isPickingLocation={isPickingLocation}
            focusCoordinates={focusCoordinates}
          />

          {/* Floating Layer Controls */}
          <div className="absolute bottom-6 left-6 z-10">
            <LayerControls />
          </div>
        </main>

        {/* Right Collapsible Operations & Detail Sidebar */}
        <aside className="h-full z-10 shadow-2xl flex flex-col w-80 lg:w-96 bg-slate-950 border-l border-slate-800">
          {/* Tab Switcher */}
          <div className="flex border-b border-slate-800 bg-slate-900/90 p-1.5 text-xs gap-1 flex-shrink-0">
            <button
              type="button"
              onClick={() => setSidebarTab('briefing')}
              className={`flex-1 py-1.5 px-3 rounded-md font-medium transition-colors flex items-center justify-center gap-1.5 ${
                sidebarTab === 'briefing'
                  ? 'bg-amber-500/20 text-amber-300 border border-amber-500/40 shadow-sm'
                  : 'text-slate-400 hover:text-slate-200'
              }`}
            >
              <ClipboardList className="w-3.5 h-3.5" />
              <span>Briefing & Runs</span>
            </button>
            <button
              type="button"
              onClick={() => setSidebarTab('details')}
              className={`flex-1 py-1.5 px-3 rounded-md font-medium transition-colors flex items-center justify-center gap-1.5 ${
                sidebarTab === 'details'
                  ? 'bg-blue-500/20 text-blue-300 border border-blue-500/40 shadow-sm'
                  : 'text-slate-400 hover:text-slate-200'
              }`}
            >
              <FileText className="w-3.5 h-3.5" />
              <span>Event Details</span>
            </button>
          </div>

          {/* Tab Content */}
          <div className="flex-1 overflow-hidden">
            {sidebarTab === 'briefing' ? (
              <div className="flex flex-col h-full overflow-y-auto">
                <div className="p-3 border-b border-slate-800/80 bg-slate-900/40 flex-shrink-0">
                  <RunTimeline eventId={selectedEvent?.id} />
                </div>
                <div className="flex-1 overflow-hidden min-h-[350px]">
                  <BriefingPanel
                    eventId={selectedEvent?.id}
                    onFocusCoordinates={setFocusCoordinates}
                  />
                </div>
              </div>
            ) : (
              <EventDetailPanel
                event={selectedEvent}
                hazardZones={hazardZonesData?.items || []}
                reports={reportsData?.items || []}
                onAddHazardZone={() => setIsNewHazardOpen(true)}
                onOpenReportModal={() => setIsSubmitReportOpen(true)}
              />
            )}
          </div>
        </aside>
      </div>

      {/* Citizen Emergency Assistant Chat Drawer */}
      <CitizenChatDrawer eventId={selectedEvent?.id} />

      {/* Modals */}
      <LoginModal isOpen={isLoginOpen} onClose={() => setIsLoginOpen(false)} />

      <div className={isPickingLocation ? 'hidden' : ''}>
        <EventCreateModal
          isOpen={isNewEventOpen}
          onClose={() => setIsNewEventOpen(false)}
          onSuccess={() => refetchEvents()}
          onStartLocationPick={handleStartLocationPick}
        />

        <ReportSubmissionModal
          isOpen={isSubmitReportOpen}
          eventId={selectedEvent?.id}
          onClose={() => setIsSubmitReportOpen(false)}
          onSuccess={() => {
            refetchReports();
            refetchEvents();
          }}
          onStartLocationPick={handleStartLocationPick}
        />
      </div>

      {selectedEvent && (
        <HazardZoneCreateModal
          isOpen={isNewHazardOpen}
          eventId={selectedEvent.id}
          onClose={() => setIsNewHazardOpen(false)}
          onSuccess={() => refetchHazards()}
        />
      )}
    </div>
  );
};

export const App: React.FC = () => {
  return (
    <QueryClientProvider client={queryClient}>
      <Dashboard />
    </QueryClientProvider>
  );
};

export default App;

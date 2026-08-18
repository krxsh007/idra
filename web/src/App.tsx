import React, { useEffect, useState } from 'react';
import { QueryClient, QueryClientProvider, useQuery } from '@tanstack/react-query';
import { Header } from './components/layout/Header';
import { MapContainer } from './components/map/MapContainer';
import { LayerControls } from './components/map/LayerControls';
import { EventDetailPanel } from './components/events/EventDetailPanel';
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
          <MapContainer
            activeEvent={selectedEvent}
            hazardZones={hazardZonesData?.items || []}
            reports={reportsData?.items || []}
            onMapClick={handleMapClick}
            isPickingLocation={isPickingLocation}
          />

          {/* Floating Layer Controls */}
          <div className="absolute bottom-6 left-6 z-10">
            <LayerControls />
          </div>
        </main>

        {/* Right Collapsible Event Detail Sidebar */}
        <aside className="h-full z-10 shadow-2xl">
          <EventDetailPanel
            event={selectedEvent}
            hazardZones={hazardZonesData?.items || []}
            reports={reportsData?.items || []}
            onAddHazardZone={() => setIsNewHazardOpen(true)}
            onOpenReportModal={() => setIsSubmitReportOpen(true)}
          />
        </aside>
      </div>

      {/* Modals */}
      <LoginModal isOpen={isLoginOpen} onClose={() => setIsLoginOpen(false)} />

      <EventCreateModal
        isOpen={isNewEventOpen}
        onClose={() => setIsNewEventOpen(false)}
        onSuccess={() => refetchEvents()}
        onStartLocationPick={handleStartLocationPick}
      />

      {selectedEvent && (
        <HazardZoneCreateModal
          isOpen={isNewHazardOpen}
          eventId={selectedEvent.id}
          onClose={() => setIsNewHazardOpen(false)}
          onSuccess={() => refetchHazards()}
        />
      )}

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

import { create } from 'zustand';
import { DisasterEvent, EventStatus } from '../types/api';

interface EventState {
  activeEventId: string | null;
  selectedEvent: DisasterEvent | null;
  statusFilter: EventStatus | 'ALL';
  setActiveEvent: (event: DisasterEvent | null) => void;
  setStatusFilter: (status: EventStatus | 'ALL') => void;
}

export const useEventStore = create<EventState>((set) => ({
  activeEventId: null,
  selectedEvent: null,
  statusFilter: 'ALL',

  setActiveEvent: (event: DisasterEvent | null) => {
    set({
      selectedEvent: event,
      activeEventId: event ? event.id : null,
    });
  },

  setStatusFilter: (status: EventStatus | 'ALL') => {
    set({ statusFilter: status });
  },
}));

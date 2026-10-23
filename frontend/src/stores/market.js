import { defineStore } from 'pinia';
import { ref } from 'vue';
import { createMarketModule } from '../modules/market.js';

export const useMarketStore = defineStore('market', () => {
  const marketSummary = ref({});
  const alertRules = ref([]);
  const alertEvents = ref([]);
  const marketLoading = ref(false);
  const alertChecking = ref(false);
  const alertEventsLoading = ref(false);
  const alertEditDialog = ref(false);
  const triggeredAlerts = ref([]);
  const alertEventCodeFilter = ref('');
  const alertEventStartDate = ref('');
  const alertEventEndDate = ref('');
  const watchlistDraft = ref([]);
  const watchlistSaving = ref(false);
  const alertForm = ref({
    target_type: 'holding',
    rule_type: 'price',
    code: '',
    name: '',
    condition: 'above',
    threshold: 0,
    enabled: true,
  });

  const moduleActions = createMarketModule({
    marketSummary,
    alertRules,
    alertEvents,
    marketLoading,
    alertChecking,
    alertEventsLoading,
    alertForm,
    alertEditDialog,
    triggeredAlerts,
    alertEventCodeFilter,
    alertEventStartDate,
    alertEventEndDate,
    watchlistDraft,
    watchlistSaving,
  });

  return {
    marketSummary,
    alertRules,
    alertEvents,
    marketLoading,
    alertChecking,
    alertEventsLoading,
    alertForm,
    alertEditDialog,
    triggeredAlerts,
    alertEventCodeFilter,
    alertEventStartDate,
    alertEventEndDate,
    watchlistDraft,
    watchlistSaving,
    ...moduleActions,
  };
});

import { ref } from "vue";

// Module-level singletons — shared across routes, survive tab navigation
const selectedList = ref("all");
const searchText = ref("");
const startDate = ref("");
const endDate = ref("");
const dateRange = ref<{ from: string; to: string } | null>(null);
const rangeDays = ref(7);
const activeWindow = ref<string | null>("7d");

export function useSharedControls() {
  return { selectedList, searchText, startDate, endDate, dateRange, rangeDays, activeWindow };
}

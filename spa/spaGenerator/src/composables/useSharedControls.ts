import { ref } from "vue";

// Module-level singletons — shared across routes, survive tab navigation
const selectedList = ref("all");
const selectedLists = ref<string[]>([]);
const searchText = ref("");
const startDate = ref("");
const endDate = ref("");
const rangeDays = ref(7);
const activeWindow = ref<string | null>("7d");

export function useSharedControls() {
  return { selectedList, selectedLists, searchText, startDate, endDate, rangeDays, activeWindow };
}

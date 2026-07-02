<template>
  <div class="heatmap-wrap">
    <div class="heatmap-grid" :style="gridStyle">
      <!-- Header: empty corner + bucket labels -->
      <div class="hm-corner" />
      <div
        v-for="(label, bi) in bucketLabels"
        :key="bi"
        class="hm-header"
        :title="isoLabel(bucketStarts[bi])"
      >
        {{ label }}
      </div>

      <!-- Data rows -->
      <template v-for="st in stations" :key="st.geosncl">
        <div class="hm-label" :title="st.geosncl">{{ st.geosncl }}</div>
        <div
          v-for="(bucket, ci) in st.buckets"
          :key="ci"
          class="hm-data"
          :style="{ background: colorFn(bucket) }"
          :title="tooltipFn(st.geosncl, bucket)"
        />
      </template>
    </div>
  </div>
</template>

<script setup lang="ts">
import { computed } from "vue";
import type { StationCompleteness, BucketData } from "../types";

const props = defineProps<{
  stations: StationCompleteness[];
  bucketStarts: number[];
  colorFn: (bucket: BucketData) => string;
  tooltipFn: (geosncl: string, bucket: BucketData) => string;
}>();

const LABEL_COL_W = 165;

const gridStyle = computed(() => ({
  gridTemplateColumns: `${LABEL_COL_W}px repeat(${props.bucketStarts.length}, minmax(5px, 1fr))`,
}));

const bucketLabels = computed((): string[] => {
  const starts = props.bucketStarts;
  const n = starts.length;
  if (n === 0) return [];
  const spanMs = n > 1 ? starts[n - 1] - starts[0] : 0;
  const multiDay = spanMs > 23 * 3_600_000;
  const step = Math.max(1, Math.floor(n / 12));
  return starts.map((ts, i) => {
    if (i % step !== 0 && i !== n - 1) return "";
    const d = new Date(ts);
    return multiDay
      ? d.toLocaleDateString([], { month: "short", day: "numeric" }) +
          " " +
          d.toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" })
      : d.toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" });
  });
});

function isoLabel(epochMs: number): string {
  return new Date(epochMs).toISOString().replace("T", " ").slice(0, 16) + " UTC";
}
</script>

<style scoped>
.heatmap-wrap {
  overflow-x: auto;
}

.heatmap-grid {
  display: grid;
  gap: 1px;
  background: #e0e0e0;
  border: 1px solid #e0e0e0;
  border-radius: 4px;
  min-width: max-content;
}

.hm-corner {
  background: #fff;
  min-height: 18px;
}

.hm-header {
  background: #fff;
  font-size: 9px;
  color: #888;
  padding: 2px;
  white-space: nowrap;
  overflow: hidden;
  writing-mode: vertical-rl;
  text-orientation: mixed;
  transform: rotate(180deg);
  height: 52px;
  display: flex;
  align-items: center;
}

.hm-label {
  background: #fff;
  font-size: 11px;
  padding: 2px 6px;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
  font-family: monospace;
  display: flex;
  align-items: center;
  min-height: 18px;
}

.hm-data {
  cursor: crosshair;
  transition: opacity 0.08s;
  min-height: 18px;
}
.hm-data:hover {
  opacity: 0.7;
  outline: 1px solid #1565c0;
  z-index: 1;
}
</style>

<template>
  <ESLayout app-name="GNSS Positions" :hide-login="true">
    <template #pre-page>
      <div class="nav-bar">
        <q-tabs dense align="left" class="nav-tabs" no-caps>
          <q-route-tab to="/overview"        label="Overview" />
          <q-route-tab to="/station-builder" label="Station Builder" />
          <q-route-tab to="/completeness"    label="Completeness" />
          <q-route-tab to="/positions"       label="Positions" />
          <q-route-tab to="/ppsd"            label="PPSD" />
          <q-route-tab to="/plots"           label="File Plots" />
          <q-route-tab to="/replay"          label="Replay" />
        </q-tabs>
      </div>
    </template>
  </ESLayout>
</template>

<script setup lang="ts">
import { ESLayout } from "@earthscope/spa-lib";
</script>

<style scoped>
.nav-bar {
  background: #1a237e;
  border-bottom: 1px solid rgba(255,255,255,0.15);
}
.nav-tabs :deep(.q-tab) {
  color: rgba(255, 255, 255, 0.8);
  min-height: 38px;
  font-size: 0.82rem;
}
.nav-tabs :deep(.q-tab--active) {
  color: #fff;
}
.nav-tabs :deep(.q-tab__indicator) {
  background: #fff;
}
</style>

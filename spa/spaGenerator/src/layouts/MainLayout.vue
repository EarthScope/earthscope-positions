<template>
  <ESLayout app-name="GNSS Positions" :hide-login="true">
    <template #pre-page>
      <!--
        ESLayout's QHeader is position:fixed (~50px tall).
        The #pre-page slot renders in the document flow at y=0, hidden under
        the fixed header. Fix: make the nav bar fixed at top:50px and force
        the page container to account for both header + nav bar height.
      -->
      <div class="nav-bar">
        <q-tabs dense align="left" class="nav-tabs" no-caps>
          <q-route-tab to="/overview"        label="Overview" />
          <q-route-tab to="/station-builder" label="Station Builder" />
          <q-route-tab to="/completeness"    label="Completeness" />
          <q-route-tab to="/positions"       label="Positions" />
          <q-route-tab to="/ppsd"            label="PPSD Generation" />
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

<style>
/*
 * ESLayout's QHeader is position:fixed with z-index ~2000.
 * Our nav bar sits just below it (z-index 1999) and also fixed.
 * The QPageContainer's padding-top (set inline by Quasar to the header
 * height ~50px) must be increased to 88px to clear both layers.
 */
.q-page-container {
  padding-top: 88px !important;
}
</style>

<style scoped>
.nav-bar {
  position: fixed;
  top: 50px;
  left: 0;
  right: 0;
  z-index: 1999;
  background: #1a237e;
  border-bottom: 1px solid rgba(255, 255, 255, 0.15);
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

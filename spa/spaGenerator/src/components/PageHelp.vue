<template>
  <div class="page-help-btn">
    <q-btn
      round flat dense
      icon="help_outline"
      color="grey-5"
      size="sm"
      @click="open = true"
    >
      <q-tooltip>How to use this page</q-tooltip>
    </q-btn>

    <q-dialog v-model="open">
      <q-card style="min-width: 360px; max-width: 540px">
        <q-card-section class="row items-center q-pb-none">
          <div class="text-h6">{{ title }}</div>
          <q-space />
          <q-btn icon="close" flat round dense v-close-popup />
        </q-card-section>
        <q-card-section class="help-body">
          <slot />
        </q-card-section>
      </q-card>
    </q-dialog>
  </div>
</template>

<script setup lang="ts">
import { ref } from "vue";
defineProps<{ title: string }>();
const open = ref(false);
</script>

<style scoped>
.page-help-btn {
  position: fixed;
  top: 96px; /* 50px ESLayout header + 38px nav bar + 8px gap */
  right: 12px;
  z-index: 1998;
}
</style>

<style>
.help-body ul {
  margin: 0;
  padding-left: 1.4em;
}
.help-body li {
  margin-bottom: 4px;
  font-size: 0.875rem;
  line-height: 1.5;
}
.help-body p {
  margin: 0 0 8px;
  font-size: 0.875rem;
  line-height: 1.5;
}
.help-body strong {
  font-weight: 600;
}
.help-section-label {
  font-size: 0.7rem;
  font-weight: 600;
  letter-spacing: 0.08em;
  text-transform: uppercase;
  color: #888;
  margin: 12px 0 4px;
}
</style>

import { createRouter, createWebHistory } from "vue-router";

const router = createRouter({
  history: createWebHistory("/"),
  routes: [
    {
      path: "/",
      component: () => import("../layouts/MainLayout.vue"),
      redirect: "/overview",
      children: [
        {
          path: "overview",
          component: () => import("../pages/OverviewPage.vue"),
        },
        {
          path: "completeness",
          component: () => import("../pages/CompletenessPage.vue"),
        },
        {
          path: "positions",
          component: () => import("../pages/PositionsPage.vue"),
        },
        {
          path: "plots",
          component: () => import("../pages/PlotsPage.vue"),
        },
        {
          path: "station-builder",
          component: () => import("../pages/StationBuilderPage.vue"),
        },
        {
          path: "replay",
          component: () => import("../pages/ReplayPage.vue"),
        },
        {
          path: "ppsd",
          component: () => import("../pages/PPSDPage.vue"),
        },
      ],
    },
    {
      path: "/:pathMatch(.*)*",
      redirect: "/overview",
    },
  ],
});

export default router;

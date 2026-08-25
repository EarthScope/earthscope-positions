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
          component: () => import("../pages/FileExplorerPage.vue"),
        },
        {
          path: "station-list-builder",
          component: () => import("../pages/StationListBuilderPage.vue"),
        },
        {
          path: "stream-list-builder",
          component: () => import("../pages/StreamListBuilderPage.vue"),
        },
        {
          // Backward-compat: old bookmarks → the station list builder.
          path: "station-builder",
          redirect: "/station-list-builder",
        },
        {
          path: "fetch-data",
          component: () => import("../pages/FetchDataPage.vue"),
        },
        {
          path: "export",
          component: () => import("../pages/ExportPage.vue"),
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

// Auto-recover from stale-build chunk errors: when a rebuild has replaced the
// hashed chunks, an already-open tab fails to lazily import a page component.
// Detect that and do a full navigation to the target so the fresh index.html +
// new chunks load. A sessionStorage guard prevents reload loops.
function isChunkLoadError(err: unknown): boolean {
  const msg = (err as Error)?.message ?? "";
  return /dynamically imported module|dynamic import|Importing a module script failed|Loading chunk|Failed to fetch/i.test(msg);
}

router.onError((error, to) => {
  if (!isChunkLoadError(error)) return;
  const target = to?.fullPath || window.location.pathname;
  const key = "chunk-reload:" + target;
  if (sessionStorage.getItem(key)) return; // already tried once — avoid a loop
  sessionStorage.setItem(key, "1");
  window.location.assign(target);
});

// Clear the one-shot guard once a navigation succeeds, so future stale builds
// can trigger a fresh reload.
router.afterEach((to) => {
  sessionStorage.removeItem("chunk-reload:" + to.fullPath);
});

export default router;

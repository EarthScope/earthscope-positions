import { createApp } from "vue";
import { Quasar, Notify } from "quasar";
import "@quasar/extras/material-icons/material-icons.css";
import "quasar/src/css/index.sass";
import App from "./App.vue";
import router from "./router";

createApp(App)
  .use(router)
  .use(Quasar, { plugins: { Notify } })
  .mount("#app");

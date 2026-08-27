import { fileURLToPath, URL } from "node:url";

import { defineConfig } from "vitest/config";
import react from "@vitejs/plugin-react";
import tailwindcss from "@tailwindcss/vite";

import { graceWindow } from "./vite-plugins/grace-window";

const root = fileURLToPath(new URL(".", import.meta.url));

export default defineConfig({
  plugins: [react(), tailwindcss(), graceWindow(root)],
  resolve: {
    // shadcn/ui components are vendored in with `@/…` imports; the alias is what makes a
    // file copied from the registry compile here without being rewritten by hand.
    alias: { "@": fileURLToPath(new URL("./src", import.meta.url)) },
  },
  test: {
    environment: "jsdom",
    globals: true,
    setupFiles: "./src/test-setup.ts",
  },
  build: {
    outDir: "../src/archcompass/presentation/web/static",
    // `false`, and the emptying is done by `graceWindow` instead. It clears everything
    // outside `assets/` exactly as this flag did, and prunes `assets/` to the previous
    // build plus the new one — so a tab that was open across a build can still fetch the
    // hashed chunk its module graph names. The plugin's header carries the argument and
    // the measured cost.
    emptyOutDir: false,
  },
  server: {
    port: 5173,
    proxy: {
      "/api": "http://127.0.0.1:8765",
    },
  },
});

import { dirname, resolve } from "node:path";
import { fileURLToPath } from "node:url";

import tailwindcss from "@tailwindcss/vite";
import react from "@vitejs/plugin-react";
import { defineConfig, loadEnv } from "vite";

export default defineConfig(({ mode }) => {
  const env = loadEnv(mode, process.cwd(), "");
  const proxyTarget = env.VITE_DEV_PROXY_TARGET || "http://127.0.0.1:8000";
  const currentDir = dirname(fileURLToPath(import.meta.url));

  return {
    // In production the SPA is served under /ui/ by nginx.
    // The base path ensures all asset references in index.html are prefixed
    // with /ui/ so nginx can find them at /var/www/ui/assets/*.
    // In development (npm run dev) the Vite server serves from root, so
    // base stays "/" to keep the dev experience unchanged.
    base: "/",

    plugins: [tailwindcss(), react()],

    resolve: {
      alias: {
        "@": resolve(currentDir, "src"),
      },
    },

    build: {
      outDir: "dist",
      sourcemap: false,
      // Split large vendor bundles into separate cacheable chunks so that
      // app code changes don't bust the cached vendor chunk in browsers.
      rollupOptions: {
        output: {
          manualChunks: {
            "vendor-react": ["react", "react-dom", "react-router-dom"],
            "vendor-query": ["@tanstack/react-query"],
            "vendor-forms": ["react-hook-form", "@hookform/resolvers", "zod"],
          },
        },
      },
    },

    test: {
      environment: "jsdom",
      setupFiles: "./src/test/setup.ts",
      css: false,
      restoreMocks: true,
      clearMocks: true,
    },

    server: {
      port: 5173,
      proxy: {
        "/api": {
          target: proxyTarget,
          changeOrigin: true,
        },
      },
    },
  };
});

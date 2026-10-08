import { defineConfig } from "vite";

/* A second build target used only to render the interface inside jsdom, so the
   data-dependent render paths can be exercised without a browser. */
export default defineConfig({
  // Render the development code paths too, so the harness sees the same branches
  // a developer running `npm run dev` would.
  define: { "import.meta.env.DEV": JSON.stringify(true) },
  build: {
    ssr: "verify/entry.jsx",
    outDir: "dist-verify",
    emptyOutDir: true,
    minify: false,
    rollupOptions: {
      output: { entryFileNames: "entry.js" },
    },
  },
});

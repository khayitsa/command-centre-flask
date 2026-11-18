import { defineConfig } from 'vite';
import react from '@vitejs/plugin-react';

// Builds straight into Flask's static folder with fixed file names (app.js / app.css);
// templates/index.html adds a cache-busting ?v= from the file's mtime.
export default defineConfig({
  plugins: [react()],
  base: '/static/dist/',
  build: {
    outDir: '../static/dist',
    emptyOutDir: true,
    cssCodeSplit: false,
    modulePreload: false,
    sourcemap: false,
    rollupOptions: {
      input: 'src/main.tsx',
      output: {
        entryFileNames: 'app.js',
        chunkFileNames: 'chunk-[hash].js',
        assetFileNames: (info) => (info.names?.some((n) => n.endsWith('.css')) ? 'app.css' : 'assets/[name]-[hash][extname]'),
      },
    },
  },
});

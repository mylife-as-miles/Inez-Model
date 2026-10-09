import { defineConfig } from 'vite';
export default defineConfig({ publicDir: '../assets', server: { host: '0.0.0.0', port: 4173 }, preview: { port: 4174 } });

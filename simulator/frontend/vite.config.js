import {defineConfig} from 'vite';
import {fileURLToPath} from 'node:url';
export default defineConfig({root:fileURLToPath(new URL('.',import.meta.url)),build:{outDir:'../web-dist',emptyOutDir:true,assetsDir:'ui-assets'},server:{host:'127.0.0.1',proxy:{'/api':'http://127.0.0.1:8765'}}});

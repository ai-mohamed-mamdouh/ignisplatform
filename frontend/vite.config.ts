import {defineConfig} from 'vite';
import react from '@vitejs/plugin-react';
import tailwind from '@tailwindcss/vite';
export default defineConfig({plugins:[react(),tailwind()],server:{port:3000,proxy:{'/api':process.env.WILDFIRE_API_PROXY ?? 'http://127.0.0.1:8000'}}});

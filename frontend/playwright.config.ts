import { defineConfig } from '@playwright/test';
export default defineConfig({
  testDir:'./e2e', timeout:60000, workers:1, reporter:'list',
  use:{baseURL:'http://127.0.0.1:18765',trace:'off'},
  projects:[{name:'desktop',use:{viewport:{width:1440,height:1000}}},{name:'mobile',use:{viewport:{width:390,height:844},isMobile:true,hasTouch:true}}],
  webServer:[
    {command:'node scripts/test-api.mjs',url:'http://127.0.0.1:18766/api/v1/health',reuseExistingServer:false},
    {command:'npm run dev -- --port 18765 --strictPort',url:'http://127.0.0.1:18765',env:{COURSE_PLANNER_API_TARGET:'http://127.0.0.1:18766'},reuseExistingServer:false},
  ],
});

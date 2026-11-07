import { spawn } from 'node:child_process';
import { resolve } from 'node:path';
const root=resolve('..');
const python=resolve(root,process.platform==='win32' ? '.venv/Scripts/python.exe' : '.venv/bin/python');
const prepare=spawn(python,['tests/make_browser_fixtures.py'],{cwd:resolve(root,'backend'),windowsHide:true,stdio:'inherit'});
prepare.on('exit',code => {
  if(code) process.exit(code);
  const api=spawn(python,['-m','uvicorn','app.main:app','--host','127.0.0.1','--port','18766'],{cwd:resolve(root,'backend'),windowsHide:true,stdio:'inherit'});
  api.on('exit',code => process.exit(code ?? 0));
  for(const signal of ['SIGINT','SIGTERM']) process.on(signal,() => api.kill());
});

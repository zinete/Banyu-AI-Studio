import fs from 'node:fs';
import os from 'node:os';
import path from 'node:path';

export function chromePath(platform = process.platform, env = process.env, exists = fs.existsSync) {
  const candidates = env.CHROME_PATH ? [env.CHROME_PATH] : platform === 'darwin'
    ? ['/Applications/Google Chrome.app/Contents/MacOS/Google Chrome',
       path.join(os.homedir(), 'Applications/Google Chrome.app/Contents/MacOS/Google Chrome')]
    : platform === 'win32'
      ? ['C:/Program Files/Google/Chrome/Application/chrome.exe',
         'C:/Program Files (x86)/Google/Chrome/Application/chrome.exe']
      : ['/usr/bin/google-chrome', '/usr/bin/chromium'];
  const executable = candidates.find(exists);
  if (!executable) throw Error('Install Google Chrome or set CHROME_PATH to its executable.');
  return executable;
}

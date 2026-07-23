import { chromium } from 'playwright-core';

const BROWSER_PATH = '/Users/roamer/Library/Caches/ms-playwright/chromium_headless_shell-1148/chrome-mac/headless_shell';
const BASE = 'http://localhost:5173';
const OUT = '/tmp/filex-showcase/screenshots';

const browser = await chromium.launch({ headless: true, executablePath: BROWSER_PATH });

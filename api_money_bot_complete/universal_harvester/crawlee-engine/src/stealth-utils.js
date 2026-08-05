/**
 * Stealth utilities: fingerprint rotation, proxy configuration, anti-detection.
 */

const { ProxyConfiguration } = require('crawlee');
const fs = require('fs-extra');
const path = require('path');

class StealthUtils {
  constructor(options = {}) {
    this.useProxy = options.useProxy || process.env.USE_PROXY === 'true';
    this.proxyUrls = (options.proxyUrls || process.env.PROXY_URLS || '').split(',').filter(Boolean);
    this.rotateFingerprint = options.rotateFingerprint !== false;
    this.headless = options.headless !== false;
    this.stealth = options.stealth !== false;
  }

  /**
   * Build Crawlee ProxyConfiguration from URLs or auto-discovery.
   */
  async buildProxyConfig() {
    if (!this.useProxy || this.proxyUrls.length === 0) {
      return undefined;
    }
    // Crawlee handles rotation automatically when given multiple URLs
    return new ProxyConfiguration({
      proxyUrls: this.proxyUrls,
    });
  }

  /**
   * Build Playwright launch options with anti-detection flags.
   */
  buildLaunchOptions() {
    const args = [
      '--disable-blink-features=AutomationControlled',
      '--disable-web-security',
      '--disable-features=IsolateOrigins,site-per-process',
      '--disable-site-isolation-trials',
      '--disable-dev-shm-usage',
      '--no-sandbox',
      '--disable-setuid-sandbox',
      '--disable-accelerated-2d-canvas',
      '--disable-gpu',
      '--window-size=1920,1080',
      '--start-maximized',
      '--hide-scrollbars',
      '--disable-notifications',
      '--disable-infobars',
      '--ignore-certificate-errors',
      '--ignore-certificate-errors-spki-list',
      '--disable-background-timer-throttling',
      '--disable-backgrounding-occluded-windows',
      '--disable-breakpad',
      '--disable-component-extensions-with-background-pages',
      '--disable-extensions',
      '--disable-features=TranslateUI',
      '--disable-ipc-flooding-protection',
      '--enable-features=NetworkService,NetworkServiceInProcess',
      '--force-color-profile=srgb',
      '--metrics-recording-only',
      '--safebrowsing-disable-auto-update',
    ];

    return {
      headless: this.headless,
      args,
      slowMo: 50,
    };
  }

  /**
   * Build browser context options with realistic fingerprint.
   */
  buildContextOptions() {
    const locales = ['en-US', 'en-GB', 'en-CA'];
    const timezones = ['America/New_York', 'America/Los_Angeles', 'Europe/London'];
    const colors = ['light', 'dark'];
    const locale = locales[Math.floor(Math.random() * locales.length)];
    const timezone = timezones[Math.floor(Math.random() * timezones.length)];
    const colorScheme = colors[Math.floor(Math.random() * colors.length)];

    const userAgents = [
      'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36',
      'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36',
      'Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:127.0) Gecko/20100101 Firefox/127.0',
    ];

    return {
      viewport: { width: 1920, height: 1080 },
      userAgent: userAgents[Math.floor(Math.random() * userAgents.length)],
      locale,
      timezoneId: timezone,
      geolocation: { latitude: 40.7128, longitude: -74.0060 },
      permissions: ['geolocation'],
      colorScheme,
      javaScriptEnabled: true,
      bypassCSP: true,
      ignoreHTTPSErrors: true,
    };
  }

  /**
   * Inject stealth scripts to hide automation.
   */
  async injectStealthScripts(page) {
    await page.addInitScript(() => {
      Object.defineProperty(navigator, 'webdriver', { get: () => undefined });
      Object.defineProperty(navigator, 'plugins', { get: () => [1, 2, 3, 4, 5] });
      window.chrome = { runtime: {} };
      Object.defineProperty(navigator, 'languages', { get: () => ['en-US', 'en'] });
      const originalQuery = window.navigator.permissions.query;
      window.navigator.permissions.query = (parameters) => (
        parameters.name === 'notifications'
          ? Promise.resolve({ state: Notification.permission })
          : originalQuery(parameters)
      );
      // Hide Playwright-specific properties
      delete window.__playwright;
      delete window.__pw_manual;
      delete window.__pw_script;
    });
  }

  /**
   * Human-like typing with random delays.
   */
  async humanType(page, selector, text) {
    const el = page.locator(selector).first();
    const count = await el.count().catch(() => 0);
    if (count === 0) return false;
    await el.click();
    await page.waitForTimeout(100 + Math.random() * 300);
    for (const char of text) {
      await el.type(char, { delay: 30 + Math.random() * 90 });
      if (char === ' ') {
        await page.waitForTimeout(150 + Math.random() * 350);
      } else if (Math.random() < 0.05) {
        await page.waitForTimeout(200 + Math.random() * 400);
      }
    }
    await page.waitForTimeout(200 + Math.random() * 300);
    return true;
  }

  /**
   * Human-like click with optional hover.
   */
  async humanClick(page, selector) {
    const el = page.locator(selector).first();
    const count = await el.count().catch(() => 0);
    if (count === 0) return false;
    if (Math.random() < 0.3) {
      await el.hover();
      await page.waitForTimeout(200 + Math.random() * 400);
    }
    await el.click();
    await page.waitForTimeout(300 + Math.random() * 500);
    return true;
  }

  /**
   * Scroll in small increments like a human.
   */
  async humanScroll(page, amount = 500) {
    const steps = 3 + Math.floor(Math.random() * 5);
    const stepSize = amount / steps;
    for (let i = 0; i < steps; i++) {
      await page.mouse.wheel(0, stepSize + (Math.random() * 40 - 20));
      await page.waitForTimeout(100 + Math.random() * 300);
    }
  }
}

module.exports = { StealthUtils };

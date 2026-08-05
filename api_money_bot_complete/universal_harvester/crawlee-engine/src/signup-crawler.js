/**
 * SignupCrawler — PlaywrightCrawler with stealth, session persistence, and form filling.
 * Handles signup, signin, and form detection across all 25 platforms.
 */

const { PlaywrightCrawler, RequestQueue, Dataset } = require('crawlee');
const { PLATFORMS } = require('./config');
const { StealthUtils } = require('./stealth-utils');
const { SessionManager } = require('./session-manager');
const fs = require('fs-extra');
const path = require('path');

const SCREENSHOT_DIR = process.env.SCREENSHOT_DIR || './screenshots';
fs.ensureDirSync(SCREENSHOT_DIR);

class SignupCrawler {
  constructor(options = {}) {
    this.stealth = new StealthUtils(options);
    this.sessions = new SessionManager();
    this.maxConcurrency = options.maxConcurrency || parseInt(process.env.MAX_CONCURRENCY, 10) || 4;
    this.timeout = options.timeout || parseInt(process.env.REQUEST_TIMEOUT, 10) || 60000;
    this.saveScreenshots = options.saveScreenshots !== false;
  }

  /**
   * Run signup/signin for a single platform.
   */
  async runPlatform(platformName, credentials, mode = 'signup') {
    const config = PLATFORMS[platformName];
    if (!config) {
      throw new Error(`Unknown platform: ${platformName}`);
    }

    const url = config[mode] || config.signup;
    const selectors = config.selectors || {};
    const results = {
      platform: platformName,
      mode,
      url,
      success: false,
      filledFields: {},
      cookies: null,
      screenshot: null,
      logs: [],
      error: null,
    };
    const proxyConfig = await this.stealth.buildProxyConfig();
    const launchOptions = this.stealth.buildLaunchOptions();
    const prevSession = await this.sessions.load(platformName);

    const crawler = new PlaywrightCrawler({
      proxyConfiguration: proxyConfig,
      launchContext: { launchOptions },
      browserPoolOptions: {
        useFingerprints: true,
        fingerprintOptions: {
          fingerprintGeneratorOptions: {
            browsers: ['chrome'],
            devices: ['desktop'],
            operatingSystems: ['windows'],
          },
        },
      },
      maxConcurrency: 1, // one platform at a time per call
      requestHandlerTimeoutSecs: this.timeout / 1000,

      async requestHandler({ page, request, log: crawlerLog }) {
        const log = (msg) => {
          crawlerLog.info(msg);
          results.logs.push(msg);
        };

        // ── Restore previous session if available ──
        if (prevSession && prevSession.cookies && prevSession.cookies.length > 0) {
          try {
            await page.context().addCookies(prevSession.cookies);
            log(`[${platformName}] Session restored (${prevSession.cookies.length} cookies)`);
          } catch (e) {
            log(`[${platformName}] Session restore failed: ${e.message}`);
          }
        }

        log(`[${platformName}] Navigating to ${url}`);
        await page.goto(url, { waitUntil: 'domcontentloaded', timeout: this.timeout });

        // Inject stealth scripts
        await this.stealth.injectStealthScripts(page);
        log(`[${platformName}] Stealth scripts injected`);

        // Random mouse wander before interaction
        await page.mouse.move(100 + Math.random() * 300, 100 + Math.random() * 300);
        await page.waitForTimeout(500 + Math.random() * 1000);

        // ── Cloudflare / anti-bot detection ──
        const title = await page.title().catch(() => '');
        const bodyText = await page.locator('body').innerText().catch(() => '');
        if (title.toLowerCase().includes('just a moment') || bodyText.toLowerCase().includes('checking your browser')) {
          log(`[${platformName}] Cloudflare challenge detected — waiting...`);
          let cleared = false;
          for (let i = 0; i < 30; i++) {
            await page.waitForTimeout(1000);
            const newTitle = await page.title().catch(() => '');
            if (!newTitle.toLowerCase().includes('just a moment')) {
              cleared = true;
              break;
            }
          }
          if (!cleared) {
            results.error = 'Cloudflare challenge not cleared';
            return;
          }
        }

        // ── Fill form fields ──
        const creds = credentials || {};

        // Email
        if (selectors.email && creds.email) {
          const filled = await this.stealth.humanType(page, selectors.email, creds.email);
          results.filledFields.email = filled;
          if (filled) log(`[${platformName}] Email filled`);
        }

        // Password
        if (selectors.password && creds.password) {
          const filled = await this.stealth.humanType(page, selectors.password, creds.password);
          results.filledFields.password = filled;
          if (filled) log(`[${platformName}] Password filled`);
        }

        // Username
        if (selectors.username && creds.username) {
          const filled = await this.stealth.humanType(page, selectors.username, creds.username);
          results.filledFields.username = filled;
          if (filled) log(`[${platformName}] Username filled`);
        }

        // First name
        if (selectors.firstName && creds.firstName) {
          const filled = await this.stealth.humanType(page, selectors.firstName, creds.firstName);
          results.filledFields.firstName = filled;
          if (filled) log(`[${platformName}] First name filled`);
        }

        // Last name
        if (selectors.lastName && creds.lastName) {
          const filled = await this.stealth.humanType(page, selectors.lastName, creds.lastName);
          results.filledFields.lastName = filled;
          if (filled) log(`[${platformName}] Last name filled`);
        }

        // ── Check terms checkboxes ──
        const checkboxes = await page.locator('input[type="checkbox"]').all();
        for (const cb of checkboxes) {
          const label = await cb.locator('xpath=ancestor::label').innerText().catch(() => '');
          const ariaLabel = await cb.getAttribute('aria-label').catch(() => '');
          const combined = (label + ' ' + ariaLabel).toLowerCase();
          const keywords = ['agree', 'terms', 'accept', 'consent', 'privacy', 'confirm', 'read and agree'];
          if (keywords.some(k => combined.includes(k))) {
            const isChecked = await cb.isChecked().catch(() => false);
            if (!isChecked) {
              await cb.click();
              log(`[${platformName}] Checked terms checkbox`);
            }
          }
        }

        // ── Submit ──
        if (selectors.submit) {
          await this.stealth.humanScroll(page, 300);
          const clicked = await this.stealth.humanClick(page, selectors.submit);
          if (clicked) {
            log(`[${platformName}] Submit clicked`);
            await page.waitForTimeout(2000 + Math.random() * 3000);
          }
        }

        // ── Screenshot ──
        if (this.saveScreenshots) {
          const screenshotPath = path.join(SCREENSHOT_DIR, `${platformName}-${Date.now()}.png`);
          await page.screenshot({ path: screenshotPath, fullPage: true });
          results.screenshot = screenshotPath;
          log(`[${platformName}] Screenshot saved: ${screenshotPath}`);
        }

        // ── Save session ──
        const sessionFile = await this.sessions.save(platformName, page.context());
        results.cookies = sessionFile;
        log(`[${platformName}] Session saved`);

        results.success = Object.values(results.filledFields).some(v => v);
      },

      async failedRequestHandler({ request, log, error }) {
        log.error(`[${platformName}] Request failed: ${error.message}`);
        results.error = error.message;
      },
    });

    // Run single request
    const queue = await RequestQueue.open();
    await queue.addRequest({ url, uniqueKey: `${platformName}-${mode}-${Date.now()}` });
    await crawler.run([queue]);
    await crawler.teardown();

    return results;
  }

  /**
   * Run multiple platforms in parallel.
   */
  async runBatch(jobs) {
    const proxyConfig = await this.stealth.buildProxyConfig();
    const launchOptions = this.stealth.buildLaunchOptions();
    const allResults = [];

    const crawler = new PlaywrightCrawler({
      proxyConfiguration: proxyConfig,
      launchContext: { launchOptions },
      browserPoolOptions: {
        useFingerprints: true,
        fingerprintOptions: {
          fingerprintGeneratorOptions: {
            browsers: ['chrome'],
            devices: ['desktop'],
            operatingSystems: ['windows'],
          },
        },
      },
      maxConcurrency: this.maxConcurrency,
      requestHandlerTimeoutSecs: this.timeout / 1000,

      async requestHandler({ page, request, log: crawlerLog }) {
        const { platformName, credentials, mode } = request.userData;
        const config = PLATFORMS[platformName];
        if (!config) {
          crawlerLog.error(`Unknown platform: ${platformName}`);
          return;
        }

        const selectors = config.selectors || {};
        const result = {
          platform: platformName,
          mode,
          url: request.url,
          success: false,
          filledFields: {},
          cookies: null,
          screenshot: null,
          logs: [],
          error: null,
        };

        // Load session
        const prevSession = await this.sessions.load(platformName);
        if (prevSession) {
          // Note: Crawlee doesn't support per-request context state easily,
          // so we skip session restore in batch mode for simplicity.
        }

        await this.stealth.injectStealthScripts(page);
        await page.mouse.move(100 + Math.random() * 300, 100 + Math.random() * 300);
        await page.waitForTimeout(500 + Math.random() * 1000);

        // Cloudflare check
        const title = await page.title().catch(() => '');
        const bodyText = await page.locator('body').innerText().catch(() => '');
        if (title.toLowerCase().includes('just a moment') || bodyText.toLowerCase().includes('checking your browser')) {
          result.logs.push(`Cloudflare detected on ${platformName}`);
          let cleared = false;
          for (let i = 0; i < 30; i++) {
            await page.waitForTimeout(1000);
            const newTitle = await page.title().catch(() => '');
            if (!newTitle.toLowerCase().includes('just a moment')) {
              cleared = true;
              break;
            }
          }
          if (!cleared) {
            result.error = 'Cloudflare challenge not cleared';
            allResults.push(result);
            return;
          }
        }

        // Fill fields
        const creds = credentials || {};
        for (const [field, selector] of Object.entries(selectors)) {
          if (['email', 'password', 'username', 'firstName', 'lastName'].includes(field) && creds[field]) {
            const filled = await this.stealth.humanType(page, selector, creds[field]);
            result.filledFields[field] = filled;
            if (filled) result.logs.push(`${field} filled`);
          }
        }

        // Check terms
        const checkboxes = await page.locator('input[type="checkbox"]').all();
        for (const cb of checkboxes) {
          const label = await cb.locator('xpath=ancestor::label').innerText().catch(() => '');
          const ariaLabel = await cb.getAttribute('aria-label').catch(() => '');
          const combined = (label + ' ' + ariaLabel).toLowerCase();
          const keywords = ['agree', 'terms', 'accept', 'consent', 'privacy', 'confirm', 'read and agree'];
          if (keywords.some(k => combined.includes(k))) {
            const isChecked = await cb.isChecked().catch(() => false);
            if (!isChecked) {
              await cb.click();
              result.logs.push('Checked terms checkbox');
            }
          }
        }

        // Submit
        if (selectors.submit) {
          await this.stealth.humanScroll(page, 300);
          const clicked = await this.stealth.humanClick(page, selectors.submit);
          if (clicked) {
            result.logs.push('Submit clicked');
            await page.waitForTimeout(2000 + Math.random() * 3000);
          }
        }

        // Screenshot
        if (this.saveScreenshots) {
          const screenshotPath = path.join(SCREENSHOT_DIR, `${platformName}-${Date.now()}.png`);
          await page.screenshot({ path: screenshotPath, fullPage: true });
          result.screenshot = screenshotPath;
        }

        // Save session
        const sessionFile = await this.sessions.save(platformName, page.context());
        result.cookies = sessionFile;
        result.success = Object.values(result.filledFields).some(v => v);
        allResults.push(result);
      },

      async failedRequestHandler({ request, log, error }) {
        const { platformName } = request.userData;
        log.error(`[${platformName}] Failed: ${error.message}`);
        allResults.push({
          platform: platformName,
          error: error.message,
          success: false,
        });
      },
    });

    const queue = await RequestQueue.open();
    for (const job of jobs) {
      await queue.addRequest({
        url: PLATFORMS[job.platform]?.[job.mode] || PLATFORMS[job.platform]?.signup,
        userData: job,
        uniqueKey: `${job.platform}-${job.mode}-${Date.now()}`,
      });
    }

    await crawler.run([queue]);
    await crawler.teardown();

    return allResults;
  }
}

module.exports = { SignupCrawler };

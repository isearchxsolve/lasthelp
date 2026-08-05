/**
 * Platform registry — 34 platforms with URL mappings and field selectors.
 * Includes trading, payment, freelance, content, e-commerce, and microtask platforms.
 */

const PLATFORMS = {
  // ═══════════════════════════════════════════════════════════
  //  CRYPTO TRADING (5)
  // ═══════════════════════════════════════════════════════════
  binance: {
    signup: 'https://accounts.binance.com/en/register',
    signin: 'https://accounts.binance.com/en/login',
    api: 'https://www.binance.com/en/my/settings/api-management',
    selectors: {
      email: 'input[type="email"], input[name="email"], input[autocomplete="email"]',
      password: 'input[type="password"], input[name="password"], input[autocomplete="new-password"]',
      submit: 'button[type="submit"], button[data-test="signup-button"]',
      terms: 'input[type="checkbox"][name*="terms" i], input[type="checkbox"][aria-label*="terms" i]',
    },
  },
  coinbase: {
    signup: 'https://login.coinbase.com/signup',
    signin: 'https://login.coinbase.com/signin',
    api: 'https://cloud.coinbase.com/access/api',
    selectors: {
      email: 'input[type="email"], input[name="email"], input[autocomplete="email"]',
      password: 'input[type="password"], input[name="password"], input[autocomplete="new-password"]',
      submit: 'button[type="submit"], button[data-test="signup-button"]',
    },
  },
  kucoin: {
    signup: 'https://www.kucoin.com/signup',
    signin: 'https://www.kucoin.com/login',
    api: 'https://www.kucoin.com/account/api',
    selectors: {
      email: 'input[type="email"], input[name="email"], input[autocomplete="email"]',
      password: 'input[type="password"], input[name="password"], input[autocomplete="new-password"]',
      submit: 'button[type="submit"], button[data-test="signup-button"]',
    },
  },
  bybit: {
    signup: 'https://www.bybit.com/en/register',
    signin: 'https://www.bybit.com/login',
    api: 'https://www.bybit.com/app/user/api-management',
    selectors: {
      email: 'input[type="email"], input[name="email"], input[autocomplete="email"]',
      password: 'input[type="password"], input[name="password"], input[autocomplete="new-password"]',
      submit: 'button[type="submit"], button[data-test="signup-button"]',
    },
  },
  okx: {
    signup: 'https://www.okx.com/join',
    signin: 'https://www.okx.com/login',
    api: 'https://www.okx.com/account/my-api',
    selectors: {
      email: 'input[type="email"], input[name="email"], input[autocomplete="email"]',
      password: 'input[type="password"], input[name="password"], input[autocomplete="new-password"]',
      submit: 'button[type="submit"], button[data-test="signup-button"]',
    },
  },

  // ═══════════════════════════════════════════════════════════
  //  FREELANCE / DEV / TECH (7)
  // ═══════════════════════════════════════════════════════════
  github: {
    signup: 'https://github.com/signup',
    signin: 'https://github.com/login',
    api: 'https://github.com/settings/tokens',
    selectors: {
      email: 'input[type="email"], input[name="user_email"], input[autocomplete="email"]',
      password: 'input[type="password"], input[name="user_password"], input[autocomplete="new-password"]',
      username: 'input[name="user_login"], input[autocomplete="username"]',
      submit: 'button[type="submit"], button[data-continue-to]',
      terms: 'input[type="checkbox"][name="terms"], input[type="checkbox"][aria-label*="terms" i]',
    },
  },
  upwork: {
    signup: 'https://www.upwork.com/nx/signup/',
    signin: 'https://www.upwork.com/ab/account-security/login',
    api: 'https://www.upwork.com/freelancers/settings/contact-info',
    selectors: {
      email: 'input[type="email"], input[name="login[username]"], input[autocomplete="email"]',
      password: 'input[type="password"], input[name="login[password]"], input[autocomplete="new-password"]',
      username: 'input[name="username"], input[autocomplete="username"]',
      firstName: 'input[name="firstName"], input[autocomplete="given-name"]',
      lastName: 'input[name="lastName"], input[autocomplete="family-name"]',
      submit: 'button[type="submit"], button[data-test="login-submit"]',
    },
  },
  freelancer: {
    signup: 'https://www.freelancer.com/signup',
    signin: 'https://www.freelancer.com/login',
    api: 'https://www.freelancer.com/developers/api_keys',
    selectors: {
      email: 'input[type="email"], input[name="email"], input[autocomplete="email"]',
      password: 'input[type="password"], input[name="password"], input[autocomplete="new-password"]',
      username: 'input[name="username"], input[autocomplete="username"]',
      submit: 'button[type="submit"], button[data-test="signup-button"]',
    },
  },
  openai: {
    signup: 'https://platform.openai.com/signup',
    signin: 'https://platform.openai.com/login',
    api: 'https://platform.openai.com/api-keys',
    selectors: {
      email: 'input[type="email"], input[name="email"], input[autocomplete="email"]',
      password: 'input[type="password"], input[name="password"], input[autocomplete="new-password"]',
      submit: 'button[type="submit"], button[data-testid="submit-button"]',
    },
  },
  anthropic: {
    signup: 'https://console.anthropic.com/register',
    signin: 'https://console.anthropic.com/login',
    api: 'https://console.anthropic.com/settings/keys',
    selectors: {
      email: 'input[type="email"], input[name="email"], input[autocomplete="email"]',
      password: 'input[type="password"], input[name="password"], input[autocomplete="new-password"]',
      submit: 'button[type="submit"], button[data-test="signup-button"]',
    },
  },
  replicate: {
    signup: 'https://replicate.com/signup',
    signin: 'https://replicate.com/login',
    api: 'https://replicate.com/account/api-tokens',
    selectors: {
      email: 'input[type="email"], input[name="email"], input[autocomplete="email"]',
      password: 'input[type="password"], input[name="password"], input[autocomplete="new-password"]',
      submit: 'button[type="submit"], button[data-test="signup-button"]',
    },
  },
  rapidapi: {
    signup: 'https://rapidapi.com/auth/sign-up',
    signin: 'https://rapidapi.com/auth/login',
    api: 'https://rapidapi.com/developer/dashboard',
    selectors: {
      email: 'input[type="email"], input[name="email"], input[autocomplete="email"]',
      password: 'input[type="password"], input[name="password"], input[autocomplete="new-password"]',
      submit: 'button[type="submit"], button[data-test="signup-button"]',
    },
  },

  // ═══════════════════════════════════════════════════════════
  //  STOCK MEDIA (3)
  // ═══════════════════════════════════════════════════════════
  shutterstock: {
    signup: 'https://submit.shutterstock.com/register',
    signin: 'https://submit.shutterstock.com/login',
    api: 'https://www.shutterstock.com/account/developers/apps',
    selectors: {
      email: 'input[type="email"], input[name="email"], input[autocomplete="email"]',
      password: 'input[type="password"], input[name="password"], input[autocomplete="new-password"]',
      submit: 'button[type="submit"], button[data-test="submit"]',
    },
  },
  adobestock: {
    signup: 'https://stock.adobe.com/contributor',
    signin: 'https://stock.adobe.com/contributor/login',
    api: 'https://developer.adobe.com/console/projects',
    selectors: {
      email: 'input[type="email"], input[name="username"], input[autocomplete="email"]',
      password: 'input[type="password"], input[name="password"], input[autocomplete="current-password"]',
      submit: 'button[type="submit"], button[data-test-id="sign-in-button"]',
    },
  },
  pond5: {
    signup: 'https://www.pond5.com/join',
    signin: 'https://www.pond5.com/login',
    api: 'https://www.pond5.com/contributor/settings',
    selectors: {
      email: 'input[type="email"], input[name="email"], input[autocomplete="email"]',
      password: 'input[type="password"], input[name="password"], input[autocomplete="new-password"]',
      submit: 'button[type="submit"], button[data-test="signup-submit"]',
    },
  },

  // ═══════════════════════════════════════════════════════════
  //  E-COMMERCE / DIGITAL PRODUCTS (7)
  // ═══════════════════════════════════════════════════════════
  gumroad: {
    signup: 'https://gumroad.com/signup',
    signin: 'https://gumroad.com/login',
    api: 'https://app.gumroad.com/settings/advanced',
    selectors: {
      email: 'input[type="email"], input[name="user[email]"], input[autocomplete="email"]',
      password: 'input[type="password"], input[name="user[password]"], input[autocomplete="new-password"]',
      submit: 'button[type="submit"], button[data-test="signup-button"]',
    },
  },
  etsy: {
    signup: 'https://www.etsy.com/join',
    signin: 'https://www.etsy.com/signin',
    api: 'https://www.etsy.com/developers/your-apps',
    selectors: {
      email: 'input[type="email"], input[name="email"], input[autocomplete="email"]',
      password: 'input[type="password"], input[name="password"], input[autocomplete="new-password"]',
      username: 'input[name="username"], input[autocomplete="username"]',
      submit: 'button[type="submit"], button[data-testid="submit"]',
    },
  },
  ebay: {
    signup: 'https://signup.ebay.com/pa/crte',
    signin: 'https://signin.ebay.com/',
    api: 'https://developer.ebay.com/my/keys',
    selectors: {
      email: 'input[type="email"], input[name="email"], input[autocomplete="email"]',
      password: 'input[type="password"], input[name="password"], input[autocomplete="new-password"]',
      submit: 'button[type="submit"], button[id="sgnBt"]',
    },
  },
  shopify: {
    signup: 'https://www.shopify.com/signup',
    signin: 'https://accounts.shopify.com/login',
    api: 'https://admin.shopify.com/settings/apps/development',
    selectors: {
      email: 'input[type="email"], input[name="email"], input[autocomplete="email"]',
      password: 'input[type="password"], input[name="password"], input[autocomplete="new-password"]',
      submit: 'button[type="submit"], button[data-testid="submit"]',
    },
  },
  printful: {
    signup: 'https://www.printful.com/signup',
    signin: 'https://www.printful.com/login',
    api: 'https://www.printful.com/dashboard/settings/api',
    selectors: {
      email: 'input[type="email"], input[name="email"], input[autocomplete="email"]',
      password: 'input[type="password"], input[name="password"], input[autocomplete="new-password"]',
      submit: 'button[type="submit"], button[data-test="signup-button"]',
    },
  },
  printify: {
    signup: 'https://printify.com/signup',
    signin: 'https://printify.com/login',
    api: 'https://printify.com/account/api',
    selectors: {
      email: 'input[type="email"], input[name="email"], input[autocomplete="email"]',
      password: 'input[type="password"], input[name="password"], input[autocomplete="new-password"]',
      submit: 'button[type="submit"], button[data-test="signup-button"]',
    },
  },
  stripe: {
    signup: 'https://dashboard.stripe.com/register',
    signin: 'https://dashboard.stripe.com/login',
    api: 'https://dashboard.stripe.com/apikeys',
    selectors: {
      email: 'input[type="email"], input[name="email"], input[autocomplete="email"]',
      password: 'input[type="password"], input[name="password"], input[autocomplete="new-password"]',
      submit: 'button[type="submit"], button[data-test="signup-button"]',
    },
  },

  // ═══════════════════════════════════════════════════════════
  //  CONTENT / SOCIAL (5)
  // ═══════════════════════════════════════════════════════════
  medium: {
    signup: 'https://medium.com/m/signup',
    signin: 'https://medium.com/m/signin',
    api: 'https://medium.com/me/settings',
    selectors: {
      email: 'input[type="email"], input[name="email"], input[autocomplete="email"]',
      password: 'input[type="password"], input[name="password"], input[autocomplete="new-password"]',
      submit: 'button[type="submit"], button[data-test="signup-button"]',
    },
  },
  patreon: {
    signup: 'https://www.patreon.com/register',
    signin: 'https://www.patreon.com/login',
    api: 'https://www.patreon.com/portal/registration/register-clients',
    selectors: {
      email: 'input[type="email"], input[name="email"], input[autocomplete="email"]',
      password: 'input[type="password"], input[name="password"], input[autocomplete="new-password"]',
      submit: 'button[type="submit"], button[data-test="signup-button"]',
    },
  },
  substack: {
    signup: 'https://substack.com/signup',
    signin: 'https://substack.com/signin',
    api: 'https://substack.com/settings',
    selectors: {
      email: 'input[type="email"], input[name="email"], input[autocomplete="email"]',
      password: 'input[type="password"], input[name="password"], input[autocomplete="new-password"]',
      submit: 'button[type="submit"], button[data-test="signup-button"]',
    },
  },
  reddit: {
    signup: 'https://www.reddit.com/register',
    signin: 'https://www.reddit.com/login',
    api: 'https://www.reddit.com/prefs/apps',
    selectors: {
      email: 'input[type="email"], input[name="email"], input[autocomplete="email"]',
      password: 'input[type="password"], input[name="password"], input[autocomplete="new-password"]',
      username: 'input[name="username"], input[autocomplete="username"]',
      submit: 'button[type="submit"], button[data-test="signup-button"]',
    },
  },
  twitter: {
    signup: 'https://twitter.com/i/flow/signup',
    signin: 'https://twitter.com/i/flow/login',
    api: 'https://developer.twitter.com/en/portal/dashboard',
    selectors: {
      email: 'input[type="email"], input[name="email"], input[autocomplete="email"]',
      password: 'input[type="password"], input[name="password"], input[autocomplete="new-password"]',
      username: 'input[name="username"], input[autocomplete="username"]',
      submit: 'button[type="submit"], button[data-test="signup-button"]',
    },
  },
  youtube: {
    signup: 'https://accounts.google.com/signup',
    signin: 'https://accounts.google.com/signin',
    api: 'https://console.cloud.google.com/apis/credentials',
    selectors: {
      email: 'input[type="email"], input[name="email"], input[autocomplete="email"]',
      password: 'input[type="password"], input[name="password"], input[autocomplete="new-password"]',
      submit: 'button[type="submit"], button[data-test="signup-button"]',
    },
  },

  // ═══════════════════════════════════════════════════════════
  //  PAYMENT / WITHDRAWAL (4)
  // ═══════════════════════════════════════════════════════════
  paypal: {
    signup: 'https://www.paypal.com/signup',
    signin: 'https://www.paypal.com/signin',
    api: 'https://developer.paypal.com/dashboard/applications',
    selectors: {
      email: 'input[type="email"], input[name="email"], input[autocomplete="email"]',
      password: 'input[type="password"], input[name="password"], input[autocomplete="new-password"]',
      submit: 'button[type="submit"], button[data-test="signup-button"]',
    },
  },
  razorpay: {
    signup: 'https://dashboard.razorpay.com/signup',
    signin: 'https://dashboard.razorpay.com/login',
    api: 'https://dashboard.razorpay.com/app/keys',
    selectors: {
      email: 'input[type="email"], input[name="email"], input[autocomplete="email"]',
      password: 'input[type="password"], input[name="password"], input[autocomplete="new-password"]',
      submit: 'button[type="submit"], button[data-test="signup-button"]',
    },
  },
  wise: {
    signup: 'https://wise.com/register',
    signin: 'https://wise.com/login',
    api: 'https://wise.com/settings/api-keys',
    selectors: {
      email: 'input[type="email"], input[name="email"], input[autocomplete="email"]',
      password: 'input[type="password"], input[name="password"], input[autocomplete="new-password"]',
      submit: 'button[type="submit"], button[data-test="signup-button"]',
    },
  },

  // ═══════════════════════════════════════════════════════════
  //  MICROTASKS (3)
  // ═══════════════════════════════════════════════════════════
  toloka: {
    signup: 'https://toloka.yandex.com/requester/registration',
    signin: 'https://toloka.yandex.com/requester/login',
    api: 'https://toloka.yandex.com/profile',
    selectors: {
      email: 'input[type="email"], input[name="email"], input[autocomplete="email"]',
      password: 'input[type="password"], input[name="password"], input[autocomplete="new-password"]',
      submit: 'button[type="submit"], button[data-test="signup-button"]',
    },
  },
  clickworker: {
    signup: 'https://www.clickworker.com/register',
    signin: 'https://www.clickworker.com/login',
    api: 'https://www.clickworker.com/settings/api',
    selectors: {
      email: 'input[type="email"], input[name="email"], input[autocomplete="email"]',
      password: 'input[type="password"], input[name="password"], input[autocomplete="new-password"]',
      submit: 'button[type="submit"], button[data-test="signup-button"]',
    },
  },
  remotasks: {
    signup: 'https://remotasks.com/register',
    signin: 'https://remotasks.com/login',
    api: 'https://www.remotasks.com/settings/api',
    selectors: {
      email: 'input[type="email"], input[name="email"], input[autocomplete="email"]',
      password: 'input[type="password"], input[name="password"], input[autocomplete="new-password"]',
      submit: 'button[type="submit"], button[data-test="signup-button"]',
    },
  },
};

module.exports = { PLATFORMS };

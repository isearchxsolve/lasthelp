import { describe, it, expect } from "bun:test";

// Test-only mock of Firebase config in require.cache so production src/config/firebase.js
// remains 100% fail-closed without any fallback scaffolding.
const firebasePath = require.resolve("../src/config/firebase");
require.cache[firebasePath] = {
  id: firebasePath,
  filename: firebasePath,
  loaded: true,
  exports: {
    db: {
      collection: () => ({
        doc: () => ({ set: async () => {} }),
        where: () => ({ where: () => ({ limit: () => ({ get: async () => ({ empty: true, docs: [] }) }) }) })
      })
    },
    admin: {},
    auth: () => ({}),
    messaging: () => ({})
  }
};

const { extractHostname, isHostMatch } = require("../src/routes/web_filter");

describe("Web Filter Hostname Security & Bypass Suite", () => {
  const allowlistRule = ["wikipedia.org"];
  const blocklistRule = ["wikipedia.org"];

  // Helper simulating the route decision logic
  function evaluateUrl(url, mode, sites) {
    const hostname = extractHostname(url);
    if (!hostname) {
      return { status: 400, error: "Invalid URL provided" };
    }

    if (mode === "allowlist") {
      const allowed = sites.some(site => isHostMatch(hostname, site));
      return {
        status: 200,
        blocked: !allowed,
        reason: allowed ? null : "Site not in allowlist",
        mode: "allowlist",
        hostname,
      };
    } else {
      const blocked = sites.some(site => isHostMatch(hostname, site));
      return {
        status: 200,
        blocked,
        reason: blocked ? "Site is blocked" : null,
        mode: "blocklist",
        hostname,
      };
    }
  }

  describe("extractHostname", () => {
    it("should correctly extract hostnames from full URLs with schemes", () => {
      expect(extractHostname("https://wikipedia.org")).toBe("wikipedia.org");
      expect(extractHostname("http://chat.wikipedia.org/path?query=1")).toBe("chat.wikipedia.org");
    });

    it("should correctly extract hostnames from bare domains and paths", () => {
      expect(extractHostname("wikipedia.org")).toBe("wikipedia.org");
      expect(extractHostname("evil.com/wikipedia.org")).toBe("evil.com");
      expect(extractHostname("  youtube.com/watch  ")).toBe("youtube.com");
    });

    it("should return null on invalid, empty, or non-string inputs", () => {
      expect(extractHostname("")).toBeNull();
      expect(extractHostname("   ")).toBeNull();
      expect(extractHostname(null)).toBeNull();
      expect(extractHostname(undefined)).toBeNull();
      expect(extractHostname("http://")).toBeNull();
    });
  });

  describe("Allowlist Security & Bypass Scenarios", () => {
    it("must REJECT 'wikipedia.org.attacker.com' against allowlist 'wikipedia.org' (deceptive subdomain bypass)", () => {
      const result = evaluateUrl("https://wikipedia.org.attacker.com", "allowlist", allowlistRule);
      expect(result.status).toBe(200);
      expect(result.blocked).toBe(true);
      expect(result.reason).toBe("Site not in allowlist");
      expect(isHostMatch(extractHostname("https://wikipedia.org.attacker.com"), "wikipedia.org")).toBe(false);
    });

    it("must ACCEPT 'chat.wikipedia.org' against allowlist 'wikipedia.org' (legitimate subdomain match)", () => {
      const result = evaluateUrl("https://chat.wikipedia.org", "allowlist", allowlistRule);
      expect(result.status).toBe(200);
      expect(result.blocked).toBe(false);
      expect(result.reason).toBeNull();
      expect(isHostMatch(extractHostname("https://chat.wikipedia.org"), "wikipedia.org")).toBe(true);
    });

    it("must REJECT 'notwikipedia.org' against allowlist 'wikipedia.org' (prefix injection case)", () => {
      const result = evaluateUrl("https://notwikipedia.org", "allowlist", allowlistRule);
      expect(result.status).toBe(200);
      expect(result.blocked).toBe(true);
      expect(result.reason).toBe("Site not in allowlist");
      expect(isHostMatch(extractHostname("https://notwikipedia.org"), "wikipedia.org")).toBe(false);
    });

    it("must REJECT 'evil.com/wikipedia.org' against allowlist 'wikipedia.org' (path match bypass)", () => {
      const result = evaluateUrl("https://evil.com/wikipedia.org", "allowlist", allowlistRule);
      expect(result.status).toBe(200);
      expect(result.blocked).toBe(true);
      expect(result.reason).toBe("Site not in allowlist");
      expect(isHostMatch(extractHostname("https://evil.com/wikipedia.org"), "wikipedia.org")).toBe(false);
    });
  });

  describe("Blocklist Security & Bypass Scenarios", () => {
    it("must NOT block 'wikipedia.org.attacker.com' when only 'wikipedia.org' is blocked", () => {
      const result = evaluateUrl("https://wikipedia.org.attacker.com", "blocklist", blocklistRule);
      expect(result.status).toBe(200);
      expect(result.blocked).toBe(false);
    });

    it("must BLOCK 'chat.wikipedia.org' when 'wikipedia.org' is blocked (subdomain inheritance)", () => {
      const result = evaluateUrl("https://chat.wikipedia.org", "blocklist", blocklistRule);
      expect(result.status).toBe(200);
      expect(result.blocked).toBe(true);
      expect(result.reason).toBe("Site is blocked");
    });

    it("must NOT block 'notwikipedia.org' when 'wikipedia.org' is blocked", () => {
      const result = evaluateUrl("https://notwikipedia.org", "blocklist", blocklistRule);
      expect(result.status).toBe(200);
      expect(result.blocked).toBe(false);
    });

    it("must NOT block 'evil.com/wikipedia.org' when 'wikipedia.org' is blocked", () => {
      const result = evaluateUrl("https://evil.com/wikipedia.org", "blocklist", blocklistRule);
      expect(result.status).toBe(200);
      expect(result.blocked).toBe(false);
    });
  });

  describe("Input Validation & Error Handling", () => {
    it("must return 400 for malformed or empty URLs", () => {
      expect(evaluateUrl("", "allowlist", allowlistRule).status).toBe(400);
      expect(evaluateUrl("   ", "allowlist", allowlistRule).status).toBe(400);
      expect(evaluateUrl(null, "allowlist", allowlistRule).status).toBe(400);
      expect(evaluateUrl(undefined, "allowlist", allowlistRule).status).toBe(400);
      expect(evaluateUrl("http://", "allowlist", allowlistRule).status).toBe(400);
    });

    it("should handle varied rule formats stored in Firestore (wildcards, protocols, trailing slashes)", () => {
      // Stored rule formats: bare domain, wildcard, full URL, trailing slash
      expect(isHostMatch("chat.wikipedia.org", "*.wikipedia.org")).toBe(true);
      expect(isHostMatch("wikipedia.org", "https://wikipedia.org/")).toBe(true);
      expect(isHostMatch("en.wikipedia.org", "wikipedia.org/wiki/Main")).toBe(true);
      expect(isHostMatch("attacker.com", "wikipedia.org")).toBe(false);
    });
  });
});

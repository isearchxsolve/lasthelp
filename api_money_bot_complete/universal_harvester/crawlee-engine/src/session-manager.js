/**
 * Session persistence manager — saves/loads cookies and localStorage per platform.
 */

const fs = require('fs-extra');
const path = require('path');

const SESSION_DIR = process.env.SESSION_DIR || './sessions';

class SessionManager {
  constructor() {
    this.dir = SESSION_DIR;
    fs.ensureDirSync(this.dir);
  }

  sessionPath(platform) {
    return path.join(this.dir, `${platform}.json`);
  }

  async save(platform, context) {
    const state = await context.storageState();
    const file = this.sessionPath(platform);
    await fs.writeJson(file, state, { spaces: 2 });
    return file;
  }

  async load(platform) {
    const file = this.sessionPath(platform);
    if (await fs.pathExists(file)) {
      return await fs.readJson(file);
    }
    return null;
  }

  async exists(platform) {
    return await fs.pathExists(this.sessionPath(platform));
  }

  async delete(platform) {
    const file = this.sessionPath(platform);
    if (await fs.pathExists(file)) {
      await fs.remove(file);
    }
  }

  async list() {
    const files = await fs.readdir(this.dir);
    return files.filter(f => f.endsWith('.json')).map(f => f.replace('.json', ''));
  }
}

module.exports = { SessionManager };

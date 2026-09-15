import fs from 'node:fs';
import fsp from 'node:fs/promises';
import path from 'node:path';
import { logger } from '../utils/logger.js';

/**
 * Small durable key/value store backed by one JSON file.
 * Writes are debounced and atomic (temp file + rename) so a crash mid-write
 * cannot leave a half-written file behind.
 */
export class JsonStore {
  #file;
  #data;
  #timer = null;
  #writing = null;
  #delay;

  constructor(file, { debounceMs = 400, initial = {} } = {}) {
    this.#file = file;
    this.#delay = debounceMs;
    this.#data = this.#load(initial);
  }

  #load(initial) {
    try {
      const raw = fs.readFileSync(this.#file, 'utf8');
      return { ...initial, ...JSON.parse(raw) };
    } catch (error) {
      if (error.code !== 'ENOENT') {
        logger.warn('تعذر قراءة ملف التخزين، سيتم البدء من جديد', {
          file: this.#file,
          error: error.message,
        });
      }
      return { ...initial };
    }
  }

  get data() {
    return this.#data;
  }

  get(key, fallback) {
    return Object.hasOwn(this.#data, key) ? this.#data[key] : fallback;
  }

  set(key, value) {
    this.#data[key] = value;
    this.scheduleSave();
    return value;
  }

  delete(key) {
    delete this.#data[key];
    this.scheduleSave();
  }

  scheduleSave() {
    if (this.#timer) return;
    this.#timer = setTimeout(() => {
      this.#timer = null;
      this.flush().catch((error) =>
        logger.error('فشل حفظ ملف التخزين', { file: this.#file, error: error.message }),
      );
    }, this.#delay);
    if (typeof this.#timer.unref === 'function') this.#timer.unref();
  }

  async flush() {
    if (this.#timer) {
      clearTimeout(this.#timer);
      this.#timer = null;
    }
    // Serialize concurrent flushes so two writers cannot interleave renames.
    this.#writing = (this.#writing ?? Promise.resolve()).then(async () => {
      const dir = path.dirname(this.#file);
      await fsp.mkdir(dir, { recursive: true });
      const tmp = `${this.#file}.${process.pid}.tmp`;
      await fsp.writeFile(tmp, JSON.stringify(this.#data, null, 2), 'utf8');
      await fsp.rename(tmp, this.#file);
    });
    return this.#writing;
  }
}

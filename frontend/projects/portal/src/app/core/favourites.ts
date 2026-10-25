import { Injectable, signal } from '@angular/core';

/**
 * Anonymous favourites in localStorage, per host and project (plan §7.2); merged into the
 * buyer account in Phase 5. Reads are safe inside `computed` (they never write a signal);
 * `version` changes on every toggle so dependent views update.
 */
@Injectable({ providedIn: 'root' })
export class Favourites {
  private readonly version = signal(0);
  private readonly cache = new Map<string, string[]>();

  list(slug: string): string[] {
    this.version();
    let v = this.cache.get(slug);
    if (!v) {
      v = read(slug);
      this.cache.set(slug, v);
    }
    return v;
  }

  has(slug: string, code: string): boolean {
    return this.list(slug).includes(code);
  }

  toggle(slug: string, code: string): void {
    const cur = this.list(slug);
    const next = cur.includes(code) ? cur.filter((c) => c !== code) : [...cur, code];
    this.cache.set(slug, next);
    try {
      localStorage.setItem(key(slug), JSON.stringify(next));
    } catch {
      /* storage unavailable: favourites last for this page only */
    }
    this.version.update((n) => n + 1);
  }
}

function key(slug: string): string {
  return `uf:fav:${location.host}:${slug}`;
}

function read(slug: string): string[] {
  try {
    const v = JSON.parse(localStorage.getItem(key(slug)) ?? '[]');
    return Array.isArray(v) ? v.filter((x) => typeof x === 'string') : [];
  } catch {
    return [];
  }
}

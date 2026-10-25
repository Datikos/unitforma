import { Injectable, computed, inject, signal } from '@angular/core';
import { UnitformaApi, type MeOut } from 'api-client';

/** Current staff principal as reported by GET /api/v1/admin/me. */
@Injectable({ providedIn: 'root' })
export class SessionStore {
  private readonly api = inject(UnitformaApi);
  readonly me = signal<MeOut | null>(null);
  readonly loaded = signal(false);
  readonly isPlatformAdmin = computed(() => this.me()?.is_platform_admin ?? false);

  async refresh(): Promise<MeOut | null> {
    try {
      const me = await this.api.me();
      this.me.set(me);
      return me;
    } catch {
      this.me.set(null);
      return null;
    } finally {
      this.loaded.set(true);
    }
  }

  clear(): void {
    this.me.set(null);
  }
}

import { HttpClient, HttpErrorResponse } from '@angular/common/http';
import { Injectable, inject } from '@angular/core';
import { firstValueFrom } from 'rxjs';

/** Subset of the Ory Kratos UI node model we render (plan §8.2). */
export interface KratosUiText {
  id: number;
  text: string;
  type: 'info' | 'error' | 'success';
}
export interface KratosUiNode {
  type: 'input' | 'text' | 'img' | 'a' | 'script';
  group: string;
  attributes: {
    name: string;
    type: string;
    value?: unknown;
    required?: boolean;
    disabled?: boolean;
    autocomplete?: string;
    node_type: string;
  };
  messages: KratosUiText[];
  meta: { label?: KratosUiText };
}
export interface KratosFlow {
  id: string;
  type: 'browser' | 'api';
  expires_at: string;
  requested_aal?: string;
  ui: { action: string; method: string; nodes: KratosUiNode[]; messages?: KratosUiText[] };
}

/** Kratos public API is proxied on the same host under /.ory/ so its cookies are first-party. */
export const KRATOS_BASE = '/.ory';

@Injectable({ providedIn: 'root' })
export class KratosService {
  private readonly http = inject(HttpClient);

  /** Start a browser flow; Kratos answers with a redirect to the UI URL carrying ?flow=. */
  startBrowserFlow(kind: 'login' | 'registration' | 'settings' | 'recovery' | 'verification', params: Record<string, string> = {}): void {
    const q = new URLSearchParams({ ...params }).toString();
    window.location.assign(`${KRATOS_BASE}/self-service/${kind}/browser${q ? `?${q}` : ''}`);
  }

  getFlow(kind: 'login' | 'registration' | 'settings' | 'recovery' | 'verification', id: string): Promise<KratosFlow> {
    return firstValueFrom(this.http.get<KratosFlow>(`${KRATOS_BASE}/self-service/${kind}/flows`, { params: { id } }));
  }

  /**
   * Submit a flow form. Kratos replies 200 (done), 400 with an updated flow (e.g. "enter the code"),
   * 422 with a browser redirect, or 410 when the flow expired.
   */
  async submit(flow: KratosFlow, values: Record<string, unknown>): Promise<{ done: true } | { done: false; flow: KratosFlow } | { redirect: string }> {
    const action = flow.ui.action.replace(/^https?:\/\/[^/]+/, '');
    try {
      await firstValueFrom(this.http.post(action, values, { headers: { Accept: 'application/json' } }));
      return { done: true };
    } catch (e) {
      const err = e as HttpErrorResponse;
      if (err.status === 400 && err.error?.ui) return { done: false, flow: err.error as KratosFlow };
      if (err.status === 422 && err.error?.redirect_browser_to) return { redirect: err.error.redirect_browser_to as string };
      throw e;
    }
  }

  async logout(): Promise<void> {
    const r = await firstValueFrom(this.http.get<{ logout_url: string; logout_token: string }>(`${KRATOS_BASE}/self-service/logout/browser`));
    await firstValueFrom(this.http.get(`${KRATOS_BASE}/self-service/logout`, { params: { token: r.logout_token }, headers: { Accept: 'application/json' } }));
  }
}

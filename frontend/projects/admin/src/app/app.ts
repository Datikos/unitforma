import { Component, signal } from '@angular/core';
import { RouterOutlet } from '@angular/router';

@Component({
  selector: 'uf-root',
  imports: [RouterOutlet],
  template: `
    <header class="uf-topbar">
      <strong>Unitforma</strong>
      <span class="uf-topbar__scope">Developer workspace · {{ version() }}</span>
    </header>
    <main class="uf-main"><router-outlet /></main>
  `,
  styles: `
    .uf-topbar { display: flex; gap: 1rem; align-items: baseline; padding: 0.75rem 1rem; border-bottom: 1px solid #e5e7eb; }
    .uf-topbar__scope { color: #6b7280; font-size: 0.875rem; }
    .uf-main { padding: 1rem; }
  `,
})
export class App {
  protected readonly version = signal('v0.1 scaffold');
}

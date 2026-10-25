import { Component, signal } from '@angular/core';
import { RouterOutlet } from '@angular/router';

@Component({
  selector: 'uf-root',
  imports: [RouterOutlet],
  template: `
    <main class="uf-portal"><router-outlet /></main>
    <footer class="uf-footer">Powered by Unitforma · {{ version() }}</footer>
  `,
  styles: `
    .uf-portal { min-height: 80vh; padding: 1rem; }
    .uf-footer { padding: 1rem; color: #6b7280; font-size: 0.75rem; text-align: center; }
  `,
})
export class App {
  protected readonly version = signal('v0.1 scaffold');
}

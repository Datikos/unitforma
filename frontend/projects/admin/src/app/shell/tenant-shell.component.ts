import { Component, OnDestroy, inject, input } from '@angular/core';
import { toObservable } from '@angular/core/rxjs-interop';
import { RouterOutlet } from '@angular/router';
import { NgIcon, provideIcons } from '@ng-icons/core';
import { UF_ICONS } from 'ui';
import { TenantContext } from '../core/tenant-context';

/** Layout route `t/:tenantId`: loads the tenant into the shared context and renders the child. */
@Component({
  selector: 'uf-tenant-shell',
  imports: [RouterOutlet, NgIcon],
  viewProviders: [provideIcons(UF_ICONS)],
  template: `
    @if (ctx.error(); as e) {
      <div class="uf-alert uf-alert--bad" role="alert"><ng-icon name="lucideCircleX" />{{ e }}</div>
    }
    <router-outlet />
  `,
})
export class TenantShellComponent implements OnDestroy {
  protected readonly ctx = inject(TenantContext);
  readonly tenantId = input.required<string>();

  constructor() {
    toObservable(this.tenantId).subscribe((id) => void this.ctx.load(id));
  }

  ngOnDestroy(): void {
    this.ctx.clear();
  }
}

import { Component, OnDestroy, effect, inject, input } from '@angular/core';
import { RouterOutlet } from '@angular/router';
import { NgIcon, provideIcons } from '@ng-icons/core';
import { UF_ICONS } from 'ui';
import { ProjectContext } from '../core/project-context';

/** Layout route `projects/:projectId`: loads the project header for the menu and the breadcrumbs. */
@Component({
  selector: 'uf-project-shell',
  imports: [RouterOutlet, NgIcon],
  viewProviders: [provideIcons(UF_ICONS)],
  template: `
    @if (ctx.error(); as e) {
      <div class="uf-alert uf-alert--bad" role="alert"><ng-icon name="lucideCircleX" />{{ e }}</div>
    }
    <router-outlet />
  `,
})
export class ProjectShellComponent implements OnDestroy {
  protected readonly ctx = inject(ProjectContext);
  readonly tenantId = input.required<string>();
  readonly projectId = input.required<string>();

  constructor() {
    effect(() => void this.ctx.load(this.tenantId(), this.projectId()));
  }

  ngOnDestroy(): void {
    this.ctx.clear();
  }
}

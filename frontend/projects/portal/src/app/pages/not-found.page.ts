import { Component } from '@angular/core';
import { RouterLink } from '@angular/router';
import { EmptyStateComponent } from 'ui';

@Component({
  selector: 'uf-not-found-page',
  imports: [RouterLink, EmptyStateComponent],
  template: `<uf-empty-state
    icon="lucideCircleHelp"
    title="Page not found"
    text="This page does not exist or is no longer published."
    ><a routerLink="/" class="uf-btn">Home</a></uf-empty-state
  >`,
})
export class NotFoundPage {}

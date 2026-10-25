import { Component } from '@angular/core';
import { RouterLink } from '@angular/router';

@Component({
  selector: 'uf-not-found-page',
  imports: [RouterLink],
  template: `<section class="uf-empty"><h1>Page not found</h1><p>This page does not exist or is no longer published.</p><a routerLink="/" class="uf-btn">Home</a></section>`,
})
export class NotFoundPage {}

import { Injectable, inject, signal } from '@angular/core';
import { ActivatedRouteSnapshot, NavigationEnd, NavigationStart, Router } from '@angular/router';
import { filter } from 'rxjs';

/**
 * Data of the deepest activated route (`shell`, `guide`, `breadcrumb` keys) and the page-set
 * breadcrumb leaf. Route data merges parent → child (`paramsInheritanceStrategy: 'always'`), so a
 * leaf without its own key inherits the section's.
 */
@Injectable({ providedIn: 'root' })
export class RouteInfo {
  private readonly router = inject(Router);
  readonly data = signal<Record<string, unknown>>({});
  readonly url = signal('');
  /** Set by pages whose last crumb is dynamic ("Page 3 of Floor plans"). Cleared on navigation. */
  readonly leaf = signal<string | null>(null);

  constructor() {
    this.router.events
      .pipe(filter((e) => e instanceof NavigationStart))
      .subscribe(() => this.leaf.set(null));
    this.router.events.pipe(filter((e) => e instanceof NavigationEnd)).subscribe((e) => {
      this.url.set(e.urlAfterRedirects);
      this.data.set(deepest(this.router.routerState.snapshot.root).data);
    });
  }

  setLeaf(label: string | null): void {
    this.leaf.set(label);
  }

  str(key: string): string | null {
    const v = this.data()[key];
    return typeof v === 'string' ? v : null;
  }
}

function deepest(r: ActivatedRouteSnapshot): ActivatedRouteSnapshot {
  let s = r;
  while (s.firstChild) s = s.firstChild;
  return s;
}

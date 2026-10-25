import { inject } from '@angular/core';
import { CanActivateFn, Router } from '@angular/router';
import { SessionStore } from './session.store';

/** Route guard: requires a valid Kratos session (UX only; the API enforces authorization). */
export const staffAuthGuard: CanActivateFn = async (_route, state) => {
  const store = inject(SessionStore);
  const router = inject(Router);
  const me = store.me() ?? (await store.refresh());
  if (me) return true;
  return router.createUrlTree(['/login'], { queryParams: { return_to: state.url } });
};

export const platformAdminGuard: CanActivateFn = async () => {
  const store = inject(SessionStore);
  const router = inject(Router);
  const me = store.me() ?? (await store.refresh());
  return me?.is_platform_admin ? true : router.createUrlTree(['/']);
};

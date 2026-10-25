import { HttpInterceptorFn } from '@angular/common/http';

/** Marks same-origin API calls; the backend rejects state-changing requests without it (CSRF, plan §8.3). */
export const requestedWithInterceptor: HttpInterceptorFn = (req, next) => {
  if (req.url.startsWith('/api/')) {
    return next(req.clone({ setHeaders: { 'X-Requested-With': 'unitforma' } }));
  }
  return next(req);
};

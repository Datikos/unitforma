import { Routes } from '@angular/router';

/** Buyer portal navigation (plan §7.1). Every page is lazy so the initial bundle stays small. */
export const routes: Routes = [
  { path: '', loadComponent: () => import('./pages/home.page').then((m) => m.HomePage) },
  {
    path: 'projects/:slug',
    loadComponent: () => import('./pages/project.page').then((m) => m.ProjectPage),
  },
  {
    path: 'projects/:slug/units',
    loadComponent: () => import('./pages/units.page').then((m) => m.UnitsPage),
  },
  {
    path: 'projects/:slug/units/:code',
    loadComponent: () => import('./pages/unit.page').then((m) => m.UnitPage),
  },
  {
    path: 'projects/:slug/buildings/:code',
    loadComponent: () => import('./pages/building.page').then((m) => m.BuildingPage),
  },
  {
    path: 'projects/:slug/favourites',
    loadComponent: () => import('./pages/favourites.page').then((m) => m.FavouritesPage),
  },
  {
    path: 'how-to-use',
    loadComponent: () => import('./pages/how-to-use.page').then((m) => m.HowToUsePage),
  },
  { path: '**', loadComponent: () => import('./pages/not-found.page').then((m) => m.NotFoundPage) },
];

# Unitforma frontend

Angular 22 CLI workspace (standalone components, signals, zoneless).

| Project | Type | Purpose |
|---|---|---|
| `admin` | application | Developer administration and sales workspace (`app.unitforma.com`), container `web-admin` |
| `portal` | application | Buyer portals on `{tenant}.unitforma.com` and custom domains, container `web-portal` |
| `libs/api-client` | library | Generated from the backend OpenAPI document (do not hand-edit) |
| `libs/auth-staff` | library | Kratos browser-flow UI renderer and staff session guard |
| `libs/auth-buyer` | library | Email-code modal talking to the `/auth/*` backend-for-frontend |
| `libs/ui` | library | Design tokens, theming via CSS custom properties, layout primitives |
| `libs/plan-viewer` | library | Deep-zoom plan tiles with SVG polygon overlay (view and edit modes) |
| `libs/viewer-3d` | library | three.js wrapper: GLB loading, picking, highlight, capability detection and fallbacks |
| `libs/domain-models` | library | Shared types and formatters (money with explicit currency, areas) |

```bash
npm ci
npx ng serve admin      # http://localhost:4200
npx ng serve portal --port 4201
npx ng test admin --watch=false && npx ng test portal --watch=false
npx ng build admin --configuration production && npx ng build portal --configuration production
```

Docker images: `Dockerfile.admin`, `Dockerfile.portal` (multi-stage build → unprivileged nginx on 8080).
Requires Node 24 (Angular 22 needs `^22.22.3 || ^24.15 || ^26`).

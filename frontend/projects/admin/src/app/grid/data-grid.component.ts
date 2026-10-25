import {
  Component,
  ElementRef,
  OnDestroy,
  afterNextRender,
  effect,
  input,
  output,
  viewChild,
} from '@angular/core';
import {
  AllCommunityModule,
  GridApi,
  GridOptions,
  ModuleRegistry,
  createGrid,
  themeQuartz,
} from 'ag-grid-community';

// AG Grid Community (MIT); only Community modules are registered (plan §4.2, [VALIDATE V8])
ModuleRegistry.registerModules([AllCommunityModule]);

/**
 * Thin Angular host for an AG Grid instance created with the framework-agnostic `createGrid`
 * API, so the app does not depend on an Angular binding package that lags framework releases.
 * Row updates after the first load should go through the emitted `GridApi` (`applyTransaction`)
 * to keep selection and scroll position.
 */
@Component({
  selector: 'uf-data-grid',
  template: `<div #host class="uf-grid"></div>`,
  styles: `
    :host {
      display: block;
    }
    .uf-grid {
      width: 100%;
      height: 68vh;
      min-height: 420px;
    }
  `,
})
export class DataGridComponent<T> implements OnDestroy {
  readonly options = input.required<GridOptions<T>>();
  readonly rows = input<T[]>([]);
  readonly ready = output<GridApi<T>>();

  private readonly host = viewChild.required<ElementRef<HTMLDivElement>>('host');
  private api: GridApi<T> | null = null;

  constructor() {
    afterNextRender(() => {
      this.api = createGrid<T>(this.host().nativeElement, {
        theme: themeQuartz.withParams({
          fontFamily: "'Inter Variable', 'Noto Sans Georgian', system-ui, sans-serif",
          accentColor: '#1d4ed8',
          borderColor: '#e2e8f0',
          headerBackgroundColor: '#f8fafc',
          headerFontWeight: 600,
        }),
        ...this.options(),
        rowData: this.rows(),
      });
      this.ready.emit(this.api);
    });
    effect(() => {
      const rows = this.rows();
      this.api?.setGridOption('rowData', rows);
    });
  }

  ngOnDestroy(): void {
    this.api?.destroy();
    this.api = null;
  }
}

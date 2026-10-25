import { Component, signal } from '@angular/core';
import { TestBed } from '@angular/core/testing';
import { GridApi, GridOptions } from 'ag-grid-community';
import { DataGridComponent } from './data-grid.component';

interface Row {
  id: string;
  code: string;
  price: string | null;
}

@Component({
  imports: [DataGridComponent],
  template: `<uf-data-grid [options]="options" [rows]="rows()" (ready)="api = $event" />`,
})
class HostComponent {
  readonly rows = signal<Row[]>([
    { id: 'a', code: 'A-01-01', price: null },
    { id: 'b', code: 'A-01-02', price: '150000.00' },
  ]);
  api: GridApi<Row> | null = null;
  readonly options: GridOptions<Row> = {
    getRowId: (p) => p.data.id,
    columnDefs: [{ field: 'code' }, { field: 'price', editable: true }],
  };
}

describe('DataGridComponent', () => {
  it('creates the grid, exposes its api and applies row updates by id', async () => {
    await TestBed.configureTestingModule({ imports: [HostComponent] }).compileComponents();
    const fixture = TestBed.createComponent(HostComponent);
    fixture.detectChanges();
    await fixture.whenStable();
    const api = fixture.componentInstance.api!;
    expect(api).toBeTruthy();
    expect(api.getDisplayedRowCount()).toBe(2);
    api.applyTransaction({ update: [{ id: 'a', code: 'A-01-01', price: '99000.00' }] });
    expect(api.getRowNode('a')?.data?.price).toBe('99000.00');
    // a missing price stays null, it is not turned into 0
    expect(api.getRowNode('a')?.data && api.getRowNode('b')?.data?.price).toBe('150000.00');
    fixture.componentInstance.rows.set([{ id: 'c', code: 'B-00-01', price: null }]);
    fixture.detectChanges();
    expect(api.getDisplayedRowCount()).toBe(1);
    expect(api.getRowNode('c')?.data?.price).toBeNull();
    fixture.destroy();
    expect(api.isDestroyed()).toBe(true);
  });
});

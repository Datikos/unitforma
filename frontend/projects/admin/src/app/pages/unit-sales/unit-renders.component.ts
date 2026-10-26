import { ChangeDetectionStrategy, Component, computed, inject } from '@angular/core';
import { RenderGenerate, RenderListComponent } from '../../sales/render-list.component';
import { UnitSalesStore } from './unit-sales.store';

/** Generated 3D plan renders owned by this unit (ADR-0017 Decision 3), wired to the unit store. */
@Component({
  selector: 'uf-unit-renders',
  imports: [RenderListComponent],
  changeDetection: ChangeDetectionStrategy.OnPush,
  template: `
    <uf-render-list
      [renders]="store.renders()"
      [busy]="store.busy()"
      mode="unit"
      [choices]="choices()"
      [hint]="hint()"
      storageKey="unit-renders"
      (generate)="onGenerate($event)"
      (approve)="store.approveRender($event)"
      (reject)="store.rejectRender($event)"
    />
  `,
})
export class UnitRendersComponent {
  protected readonly store = inject(UnitSalesStore);
  readonly choices = computed(() =>
    this.store.neighbours().map((n) => ({ id: n.unit_id, code: n.code })),
  );
  readonly hint = computed(() => {
    const layout = this.store.row()?.layout;
    return layout
      ? `A render made here belongs to ${this.store.row()?.code} only (for example joined with a neighbour); the one every unit of layout ${layout} shows is made once on the Layouts page.`
      : 'A furnished 3D view made from the plan crop; private until approved, then labelled "AI generated".';
  });

  onGenerate(g: RenderGenerate): Promise<void> {
    return this.store.requestRender(g.note, g.withId);
  }
}

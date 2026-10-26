import { ChangeDetectionStrategy, Component, inject } from '@angular/core';
import { MediaListComponent, MediaUpload } from '../../sales/media-list.component';
import { UnitSalesStore } from './unit-sales.store';

/** The unit's own renders, photos and documents, wired to the unit store. */
@Component({
  selector: 'uf-unit-media',
  imports: [MediaListComponent],
  changeDetection: ChangeDetectionStrategy.OnPush,
  template: `
    <uf-media-list
      [media]="store.media()"
      [busy]="store.busy()"
      storageKey="unit-media"
      emptyText="Add renders or photos of this unit; media shared by its layout are managed on the Layouts page."
      (upload)="onUpload($event)"
      (patch)="store.patchMedia($event.m, $event.body)"
      (move)="store.move($event.i, $event.delta)"
      (remove)="store.remove($event)"
    />
  `,
})
export class UnitMediaComponent {
  protected readonly store = inject(UnitSalesStore);

  onUpload(u: MediaUpload): Promise<void> {
    return this.store.upload(u.file, u.kind, u.isPublic, u.ai);
  }
}

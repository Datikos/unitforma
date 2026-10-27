import { Injectable, OnDestroy, computed, inject, signal } from '@angular/core';
import {
  LayoutOut,
  MediaOut,
  MediaUpdate,
  RendersOut,
  UnitformaApi,
  problemMessage,
} from 'api-client';
import { httpStatus, problemBody } from '../../sales/sales-format';
import { MediaKind } from '../../sales/media-list.component';
import { DialogsService } from '../../ui/dialogs.service';
import { ToastService } from '../../ui/toast.service';
import { LayoutForm } from './layouts.model';

/** State and API calls of the Layouts page (ADR-0022); provided by the page. */
@Injectable()
export class LayoutsStore implements OnDestroy {
  private readonly api = inject(UnitformaApi);
  private readonly dialogs = inject(DialogsService);
  private readonly toast = inject(ToastService);
  private tenantId = '';
  private projectId = '';
  private pollTimer: ReturnType<typeof setTimeout> | null = null;

  readonly layouts = signal<LayoutOut[]>([]);
  readonly selectedId = signal<string | null>(null);
  readonly selected = computed(
    () => this.layouts().find((l) => l.id === this.selectedId()) ?? null,
  );
  /** Media and renders of the selected layout. */
  readonly media = signal<MediaOut[]>([]);
  readonly renders = signal<RendersOut | null>(null);
  readonly loaded = signal(false);
  readonly busy = signal(false);
  readonly error = signal<string | null>(null);

  init(tenantId: string, projectId: string): void {
    if (projectId !== this.projectId) this.selectedId.set(null);
    this.tenantId = tenantId;
    this.projectId = projectId;
  }

  async load(): Promise<void> {
    try {
      this.layouts.set(await this.api.listLayouts(this.tenantId, this.projectId));
      if (this.selectedId() && !this.selected()) this.selectedId.set(null);
      if (this.selectedId()) await this.loadDetail();
    } catch (e) {
      this.error.set(problemMessage(e));
    } finally {
      this.loaded.set(true);
    }
  }

  async select(id: string | null): Promise<void> {
    this.selectedId.set(id);
    this.media.set([]);
    this.setRenders(null);
    if (id) await this.loadDetail();
  }

  private async loadDetail(): Promise<void> {
    const id = this.selectedId();
    if (!id) return;
    try {
      const [media, renders] = await Promise.all([
        this.api.listLayoutMedia(this.tenantId, id),
        this.api.listLayoutRenders(this.tenantId, id),
      ]);
      if (this.selectedId() !== id) return;
      this.media.set(media);
      this.setRenders(renders);
    } catch (e) {
      this.error.set(problemMessage(e));
    }
  }

  create(form: LayoutForm): Promise<boolean> {
    return this.run(async () => {
      const l = await this.api.createLayout(this.tenantId, this.projectId, {
        code: form.code.trim(),
        name: form.name.trim() || null,
      });
      this.toast.ok(`Layout ${l.code} created`);
      await this.load();
      await this.select(l.id);
    });
  }

  /** A plan type the solver proposed becomes a confirmed layout (ADR-0025 Decision 6). */
  confirm(l: LayoutOut): Promise<boolean> {
    return this.run(async () => {
      await this.api.confirmLayout(this.tenantId, l.id);
      this.toast.ok(`Layout ${l.code} confirmed: it can own renders now and buyers see it`);
      await this.load();
    });
  }

  rename(l: LayoutOut, form: LayoutForm): Promise<boolean> {
    return this.run(async () => {
      await this.api.updateLayout(this.tenantId, l.id, {
        code: form.code.trim(),
        name: form.name.trim() || null,
        version: l.version,
      });
      this.toast.ok(`Layout ${form.code.trim()} saved`);
      await this.load();
    });
  }

  async remove(l: LayoutOut): Promise<void> {
    const n = l.units.length;
    const ok = await this.dialogs.confirm({
      title: `Delete layout ${l.code}?`,
      message: n
        ? `${n} ${n === 1 ? 'unit is' : 'units are'} linked to it: they are unlinked and keep their own media. The layout's ${l.media_count} media file(s) are removed now.`
        : `The layout's ${l.media_count} media file(s) are removed now.`,
      confirmLabel: n ? 'Unlink and delete' : 'Delete',
      tone: 'bad',
      icon: 'lucideTrash2',
    });
    if (!ok) return;
    await this.run(async () => {
      await this.api.deleteLayout(this.tenantId, l.id, n > 0);
      this.toast.ok(`Layout ${l.code} deleted`);
      await this.select(null);
      await this.load();
    });
  }

  // --- media ----------------------------------------------------------------------------------
  upload(file: File, kind: MediaKind, isPublic: boolean, ai: boolean): Promise<boolean> {
    const id = this.selectedId()!;
    return this.run(async () => {
      const intent = await this.api.createLayoutMedia(this.tenantId, id, {
        file_name: file.name,
        content_type: file.type || 'application/octet-stream',
        byte_size: file.size,
        kind,
        is_public: isPublic,
        is_ai_generated: ai,
      });
      await this.api.uploadToPresignedUrl(intent.upload_url, file, file.type);
      await this.api.completeMedia(this.tenantId, intent.media.id);
      this.toast.ok(`${file.name} uploaded`);
      await this.load();
    });
  }

  patchMedia(m: MediaOut, body: Omit<MediaUpdate, 'version'>): Promise<boolean> {
    return this.run(async () => {
      await this.api.updateMedia(this.tenantId, m.id, { ...body, version: m.version });
      await this.load();
    });
  }

  move(i: number, delta: number): Promise<boolean> {
    const id = this.selectedId()!;
    const ids = this.media().map((m) => m.id);
    [ids[i], ids[i + delta]] = [ids[i + delta], ids[i]];
    return this.run(async () => {
      this.media.set(await this.api.reorderLayoutMedia(this.tenantId, id, ids));
    });
  }

  async removeMedia(m: MediaOut): Promise<void> {
    const ok = await this.dialogs.confirm({
      title: `Delete ${m.file_name}?`,
      message:
        'The file is removed from this layout and from every linked unit on the next publication.',
      confirmLabel: 'Delete',
      tone: 'bad',
      icon: 'lucideTrash2',
    });
    if (!ok) return;
    await this.run(async () => {
      await this.api.deleteMedia(this.tenantId, m.id);
      this.toast.ok(`${m.file_name} deleted`);
      await this.load();
    });
  }

  // --- generated renders (ADR-0022 Decision 4) ------------------------------------------------
  private setRenders(r: RendersOut | null): void {
    this.renders.set(r);
    if (this.pollTimer) clearTimeout(this.pollTimer);
    this.pollTimer = null;
    if (r?.items.some((i) => i.status === 'queued' || i.status === 'running')) {
      this.pollTimer = setTimeout(() => void this.loadDetail(), 4000);
    }
  }

  requestRender(note: string, unitId: string | null): Promise<boolean> {
    const id = this.selectedId()!;
    return this.run(async () => {
      await this.api.requestLayoutRender(this.tenantId, id, {
        note: note.trim() || null,
        unit_id: unitId,
      });
      this.toast.ok('Render requested; it appears below when the model answers');
      await this.loadDetail();
    });
  }

  approveRender(renderId: string): Promise<boolean> {
    return this.run(async () => {
      await this.api.approveRender(this.tenantId, renderId);
      this.toast.ok('Approved: public on every linked unit with the next publication');
      await this.load();
    });
  }

  rejectRender(renderId: string): Promise<boolean> {
    return this.run(async () => {
      await this.api.rejectRender(this.tenantId, renderId);
      await this.load();
    });
  }

  ngOnDestroy(): void {
    if (this.pollTimer) clearTimeout(this.pollTimer);
    this.pollTimer = null;
  }

  /** Runs one action with the busy flag; a problem detail becomes the page error. */
  private async run(fn: () => Promise<void>): Promise<boolean> {
    this.busy.set(true);
    this.error.set(null);
    try {
      await fn();
      return true;
    } catch (e) {
      const body = problemBody(e);
      const units = body?.['units'];
      this.error.set(
        httpStatus(e) === 409 && Array.isArray(units)
          ? `${problemMessage(e)} (${units.join(', ')})`
          : problemMessage(e),
      );
      return false;
    } finally {
      this.busy.set(false);
    }
  }
}

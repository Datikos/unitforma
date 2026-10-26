import { Component, computed, inject, input, signal } from '@angular/core';
import { toObservable } from '@angular/core/rxjs-interop';
import { FormsModule } from '@angular/forms';
import { MatButtonModule } from '@angular/material/button';
import { MatFormFieldModule } from '@angular/material/form-field';
import { MatInputModule } from '@angular/material/input';
import { NgIcon, provideIcons } from '@ng-icons/core';
import { RenderPromptOut, UnitformaApi, problemMessage } from 'api-client';
import { HeaderFact, PageHeaderComponent, SectionCardComponent, UF_ICONS } from 'ui';
import { DialogsService } from '../ui/dialogs.service';
import { ToastService } from '../ui/toast.service';

const PROMPT_MAX = 4000;

/** Workspace settings (ADR-0023): the base prompt of generated 3D plan renders. */
@Component({
  selector: 'uf-settings-page',
  imports: [
    FormsModule,
    MatFormFieldModule,
    MatInputModule,
    MatButtonModule,
    NgIcon,
    PageHeaderComponent,
    SectionCardComponent,
  ],
  viewProviders: [provideIcons(UF_ICONS)],
  template: `
    <div class="uf-page">
      <uf-page-header title="Settings" icon="lucideSettings" [facts]="facts()" />
      @if (error(); as e) {
        <div class="uf-alert uf-alert--bad" role="alert">
          <ng-icon name="lucideCircleX" />{{ e }}
        </div>
      }

      <uf-section-card
        title="Generated plan renders"
        icon="lucideSparkles"
        [summary]="sourceText()"
        [collapsible]="false"
      >
        <p class="uf-hint">
          The text every generated 3D plan render starts from, for every project of this workspace.
          The plan crop is attached after it; the joined-apartment sentence, the unit's wall colour
          and the note typed on the render panel are added automatically. Changes apply from the
          next request on.
        </p>
        <mat-form-field appearance="outline" subscriptSizing="dynamic" class="prompt">
          <mat-label>Base prompt</mat-label>
          <textarea
            matInput
            [(ngModel)]="text"
            name="prompt"
            rows="9"
            [maxlength]="max"
            [disabled]="busy() || !loaded()"
            placeholder="Describe the view, the style and what must stay as drawn"
          ></textarea>
          <mat-hint align="end">{{ text.length }} / {{ max }}</mat-hint>
        </mat-form-field>
        <div class="uf-form-row actions">
          <button mat-flat-button [disabled]="busy() || !dirty() || !text.trim()" (click)="save()">
            <ng-icon name="lucideSave" /> Save
          </button>
          <button mat-button [disabled]="busy() || !isCustom()" (click)="reset()">
            <ng-icon name="lucideRotateCcw" /> Reset to default
          </button>
          @if (isCustom() && !dirty()) {
            <span class="uf-hint"> <ng-icon name="lucideCheck" /> Workspace text in use </span>
          } @else if (!isCustom() && !dirty()) {
            <span class="uf-hint">Built-in default in use; edit and save to make it yours</span>
          }
        </div>
        <p class="uf-hint">
          Keep "keep the exact wall layout, room proportions, door and window positions as drawn"
          and "no text, no labels, no dimension lines, no people": without them the model invents
          rooms and prints words, and the reviewer has to reject the image. Change one thing at a
          time; each try costs one render.
        </p>
      </uf-section-card>
    </div>
  `,
  styles: `
    .prompt {
      width: 100%;
    }
    .prompt textarea {
      font-family: var(--uf-font-mono, ui-monospace, monospace);
      font-size: 0.9rem;
      line-height: 1.45;
    }
    .actions {
      align-items: center;
      margin-top: 0.75rem;
    }
    .actions .uf-hint {
      margin: 0;
    }
    button ng-icon,
    .uf-hint ng-icon {
      vertical-align: -0.15em;
      margin-right: 0.25rem;
    }
  `,
})
export class SettingsPage {
  private readonly api = inject(UnitformaApi);
  private readonly dialogs = inject(DialogsService);
  private readonly toast = inject(ToastService);
  readonly tenantId = input.required<string>();
  readonly data = signal<RenderPromptOut | null>(null);
  readonly busy = signal(false);
  readonly error = signal<string | null>(null);
  /** The textarea's value, mirrored into a signal on every save or load. */
  readonly saved = signal('');
  readonly typed = signal('');
  readonly max = PROMPT_MAX;
  readonly loaded = computed(() => this.data() !== null);
  readonly isCustom = computed(() => this.data()?.source === 'workspace');
  readonly dirty = computed(() => this.typed().trim() !== this.saved().trim());
  readonly sourceText = computed(() => (this.isCustom() ? 'workspace text' : 'built-in default'));
  readonly facts = computed<HeaderFact[]>(() => [
    { label: 'Render prompt', value: this.sourceText() },
  ]);

  constructor() {
    toObservable(this.tenantId).subscribe(() => void this.load());
  }

  get text(): string {
    return this.typed();
  }
  set text(v: string) {
    this.typed.set(v);
  }

  async load(): Promise<void> {
    try {
      this.apply(await this.api.getRenderPrompt(this.tenantId()));
    } catch (e) {
      this.error.set(problemMessage(e));
    }
  }

  save(): Promise<void> {
    const prompt = this.typed().trim();
    if (!prompt) return Promise.resolve();
    return this.run(async () => {
      this.apply(await this.api.setRenderPrompt(this.tenantId(), { prompt }));
      this.toast.ok('Render prompt saved; the next render uses it');
    });
  }

  async reset(): Promise<void> {
    const ok = await this.dialogs.confirm({
      title: 'Reset the render prompt?',
      message: 'The workspace text is removed and renders use the built-in default again.',
      consequence: 'Your text is not kept; copy it first if you may want it back.',
      confirmLabel: 'Reset',
      tone: 'bad',
    });
    if (!ok) return;
    return this.run(async () => {
      this.apply(await this.api.setRenderPrompt(this.tenantId(), { prompt: null }));
      this.toast.ok('Render prompt reset to the default');
    });
  }

  private apply(d: RenderPromptOut): void {
    this.data.set(d);
    const text = d.prompt ?? d.default;
    this.saved.set(text);
    this.typed.set(text);
  }

  private async run(fn: () => Promise<unknown>): Promise<void> {
    this.busy.set(true);
    this.error.set(null);
    try {
      await fn();
    } catch (e) {
      this.error.set(problemMessage(e));
    } finally {
      this.busy.set(false);
    }
  }
}

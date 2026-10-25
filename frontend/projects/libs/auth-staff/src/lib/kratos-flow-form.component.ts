import { Component, computed, input, output, signal } from '@angular/core';
import { FormsModule } from '@angular/forms';
import { MatButtonModule } from '@angular/material/button';
import { MatFormFieldModule } from '@angular/material/form-field';
import { MatInputModule } from '@angular/material/input';
import type { KratosFlow, KratosUiNode } from './kratos.service';

/**
 * Renders the UI nodes of a Kratos self-service flow as a Material form.
 * Hidden inputs (csrf_token, identifier) are carried through; submit buttons emit their value.
 */
@Component({
  selector: 'uf-kratos-flow-form',
  imports: [FormsModule, MatFormFieldModule, MatInputModule, MatButtonModule],
  template: `
    @for (m of flow().ui.messages ?? []; track m.id) {
      <p class="uf-flow-msg" [class.uf-flow-msg--error]="m.type === 'error'">{{ m.text }}</p>
    }
    <form (ngSubmit)="$event.preventDefault()">
      @for (node of visibleInputs(); track node.attributes.name) {
        <mat-form-field appearance="outline" class="uf-flow-field">
          <mat-label>{{ node.meta.label?.text ?? node.attributes.name }}</mat-label>
          <input
            matInput
            [type]="node.attributes.type"
            [name]="node.attributes.name"
            [required]="node.attributes.required ?? false"
            [attr.autocomplete]="node.attributes.autocomplete ?? null"
            [attr.inputmode]="node.attributes.name === 'code' ? 'numeric' : null"
            [ngModel]="values()[node.attributes.name]"
            (ngModelChange)="set(node.attributes.name, $event)"
          />
          @for (m of node.messages; track m.id) {
            <mat-error>{{ m.text }}</mat-error>
          }
        </mat-form-field>
      }
      <div class="uf-flow-actions">
        @for (btn of submitButtons(); track btn.attributes.name + btn.attributes.value) {
          <button mat-flat-button type="button" [disabled]="busy()" (click)="submit(btn)">
            {{ btn.meta.label?.text ?? 'Continue' }}
          </button>
        }
      </div>
    </form>
  `,
  styles: `
    :host { display: block; }
    .uf-flow-field { width: 100%; }
    .uf-flow-actions { display: flex; gap: 0.5rem; flex-wrap: wrap; }
    .uf-flow-msg { margin: 0 0 1rem; }
    .uf-flow-msg--error { color: var(--mat-sys-error, #b3261e); }
  `,
})
export class KratosFlowFormComponent {
  readonly flow = input.required<KratosFlow>();
  readonly busy = input(false);
  /** Only these node groups are rendered (e.g. ['default', 'code'] for passwordless login). */
  readonly groups = input<string[] | null>(null);
  readonly submitted = output<Record<string, unknown>>();

  readonly values = signal<Record<string, unknown>>({});

  private readonly nodes = computed(() => {
    const g = this.groups();
    return this.flow().ui.nodes.filter((n) => n.type === 'input' && (!g || g.includes(n.group) || n.group === 'default'));
  });
  readonly visibleInputs = computed(() => this.nodes().filter((n) => !['hidden', 'submit', 'button'].includes(n.attributes.type)));
  readonly submitButtons = computed(() => this.nodes().filter((n) => n.attributes.type === 'submit'));

  set(name: string, value: unknown): void {
    this.values.update((v) => ({ ...v, [name]: value }));
  }

  submit(btn: KratosUiNode): void {
    const payload: Record<string, unknown> = {};
    for (const n of this.nodes()) {
      if (n.attributes.type === 'hidden') payload[n.attributes.name] = n.attributes.value;
      else if (!['submit', 'button'].includes(n.attributes.type)) {
        const v = this.values()[n.attributes.name] ?? n.attributes.value;
        if (v !== undefined && v !== '') payload[n.attributes.name] = v;
      }
    }
    payload[btn.attributes.name] = btn.attributes.value;
    this.submitted.emit(payload);
  }
}

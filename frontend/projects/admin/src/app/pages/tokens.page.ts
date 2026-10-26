import { Component, computed, inject, input, signal } from '@angular/core';
import { toObservable } from '@angular/core/rxjs-interop';
import { FormsModule } from '@angular/forms';
import { MatButtonModule } from '@angular/material/button';
import { MatFormFieldModule } from '@angular/material/form-field';
import { MatInputModule } from '@angular/material/input';
import { MatSelectModule } from '@angular/material/select';
import { NgIcon, provideIcons } from '@ng-icons/core';
import { ApiTokenCreated, ApiTokenOut, UnitformaApi, problemMessage } from 'api-client';
import { SessionStore } from 'auth-staff';
import {
  EmptyStateComponent,
  HeaderFact,
  PageHeaderComponent,
  SectionCardComponent,
  StatusChipComponent,
  UF_ICONS,
  ago,
  dayOf,
} from 'ui';
import { DialogsService } from '../ui/dialogs.service';
import { ToastService } from '../ui/toast.service';

type Scope = 'read' | 'write';
const SCOPES: { value: Scope; label: string; does: string }[] = [
  { value: 'read', label: 'Read', does: 'lists and reads projects, buildings and floors' },
  { value: 'write', label: 'Write', does: 'also creates and updates them, within your role' },
];
const EXPIRIES = [30, 90, 180, 365];

/** Personal API tokens for the MCP server at /mcp (ADR-0015 Decision 8). */
@Component({
  selector: 'uf-tokens-page',
  imports: [
    FormsModule,
    MatFormFieldModule,
    MatInputModule,
    MatSelectModule,
    MatButtonModule,
    NgIcon,
    PageHeaderComponent,
    SectionCardComponent,
    StatusChipComponent,
    EmptyStateComponent,
  ],
  viewProviders: [provideIcons(UF_ICONS)],
  template: `
    <div class="uf-page">
      <uf-page-header title="API tokens" icon="lucideKeyRound" [facts]="facts()" />
      @if (error(); as e) {
        <div class="uf-alert uf-alert--bad" role="alert">
          <ng-icon name="lucideCircleX" />{{ e }}
        </div>
      }

      <uf-section-card
        title="Connect an assistant"
        icon="lucidePlug"
        summary="the server URL and the ready commands"
        storageKey="tokens-connect"
        [open]="true"
      >
        <dl class="connect">
          <div>
            <dt>MCP server URL</dt>
            <dd class="uf-mono row">
              <code>{{ mcpUrl() }}</code>
              <button mat-button (click)="copy(mcpUrl(), 'URL copied')">
                <ng-icon name="lucideCopy" /> Copy
              </button>
            </dd>
          </div>
          <div>
            <dt>Claude Code</dt>
            <dd class="uf-mono row">
              <code>{{ claudeCommand() }}</code>
              <button mat-button (click)="copy(claudeCommand(), 'Command copied')">
                <ng-icon name="lucideCopy" /> Copy
              </button>
            </dd>
          </div>
          <div>
            <dt>.mcp.json (project or user scope)</dt>
            <dd class="uf-mono row">
              <pre>{{ mcpJson() }}</pre>
              <button mat-button (click)="copy(mcpJson(), 'JSON copied')">
                <ng-icon name="lucideCopy" /> Copy
              </button>
            </dd>
          </div>
          <div>
            <dt>Claude.ai custom connector</dt>
            <dd>
              Settings → Connectors → Add custom connector: the URL above, authentication "API key",
              header <code>Authorization: Bearer {{ tokenText() }}</code
              >.
            </dd>
          </div>
          <div>
            <dt>Test from a terminal</dt>
            <dd class="uf-mono row">
              <code>{{ curlCommand() }}</code>
              <button mat-button (click)="copy(curlCommand(), 'curl copied')">
                <ng-icon name="lucideCopy" /> Copy
              </button>
            </dd>
          </div>
        </dl>
        <p class="uf-hint">
          @if (created()) {
            The commands carry the token you just created. Copy them now: the secret is not shown
            again after you leave this page.
          } @else {
            The commands carry a placeholder: create a token below and they fill in with its secret.
            Then ask the assistant to call <code>whoami</code>.
          }
        </p>
      </uf-section-card>

      <uf-section-card
        title="Create a token"
        icon="lucidePlus"
        summary="name, scope, expiry; the secret shows once"
        storageKey="tokens-create"
        [open]="tokens().length === 0"
      >
        <div class="uf-form-row">
          <mat-form-field appearance="outline" subscriptSizing="dynamic"
            ><mat-label>Name</mat-label
            ><input
              matInput
              [(ngModel)]="name"
              name="name"
              placeholder="Claude Code on my laptop"
              maxlength="120"
              (keyup.enter)="create()"
          /></mat-form-field>
          <mat-form-field appearance="outline" subscriptSizing="dynamic"
            ><mat-label>Scope</mat-label>
            <mat-select [(ngModel)]="scope" name="scope">
              @for (s of scopes; track s.value) {
                <mat-option [value]="s.value">{{ s.label }}</mat-option>
              }
            </mat-select>
          </mat-form-field>
          <mat-form-field appearance="outline" subscriptSizing="dynamic"
            ><mat-label>Expires in</mat-label>
            <mat-select [(ngModel)]="days" name="days">
              @for (d of expiries; track d) {
                <mat-option [value]="d">{{ d }} days</mat-option>
              }
            </mat-select>
          </mat-form-field>
          <button mat-flat-button [disabled]="busy() || !name.trim()" (click)="create()">
            <ng-icon name="lucideKeyRound" /> Create token
          </button>
        </div>
        <p class="uf-hint">
          {{ scopeHelp() }}. The token acts as you ({{ me() }}); it never does more than your role
          allows, and it stops at the expiry or when revoked.
        </p>

        @if (created(); as c) {
          <div class="uf-alert uf-alert--good secret">
            <ng-icon name="lucideShieldCheck" />
            <div>
              <strong>Copy the secret now.</strong> It is shown once and never stored; the commands
              in "Connect an assistant" above carry it already.
              <div class="uf-mono row">
                <code>{{ c.secret }}</code>
                <button mat-button (click)="copy(c.secret, 'Secret copied')">
                  <ng-icon name="lucideCopy" /> Copy
                </button>
              </div>
            </div>
          </div>
        }
      </uf-section-card>

      <uf-section-card
        title="Tokens"
        icon="lucideKeyRound"
        [count]="tokens().length"
        [summary]="activeCount() + ' active'"
        [flush]="true"
        [collapsible]="false"
      >
        @if (tokens().length) {
          <table class="uf-plain">
            <thead>
              <tr>
                <th>Name</th>
                <th>Owner</th>
                <th>Prefix</th>
                <th>Scope</th>
                <th>Status</th>
                <th>Last used</th>
                <th>Expires</th>
                <th></th>
              </tr>
            </thead>
            <tbody>
              @for (t of tokens(); track t.id) {
                <tr [class.dim]="t.status !== 'active'">
                  <td>
                    <strong>{{ t.name }}</strong>
                  </td>
                  <td>{{ t.user_email }}</td>
                  <td class="uf-mono">{{ t.token_prefix }}…</td>
                  <td><uf-status-chip domain="token.scope" [value]="t.scope" /></td>
                  <td><uf-status-chip domain="token" [value]="t.status" /></td>
                  <td>{{ t.last_used_at ? since(t.last_used_at) : 'never' }}</td>
                  <td>{{ day(t.expires_at) }}</td>
                  <td class="actions">
                    @if (t.status === 'active') {
                      <button mat-button (click)="revoke(t)">
                        <ng-icon name="lucideBan" /> Revoke
                      </button>
                    }
                  </td>
                </tr>
              }
            </tbody>
          </table>
        } @else {
          <uf-empty-state
            icon="lucideKeyRound"
            title="No tokens yet"
            text="Create one above to connect an assistant or a script to this workspace."
            [compact]="true"
          />
        }
      </uf-section-card>

      <uf-section-card
        title="What the assistant can do"
        icon="lucideBot"
        summary="projects, buildings, floors, site features"
        storageKey="tokens-tools"
        [open]="false"
      >
        <p class="uf-hint">
          Tools: <code>whoami</code>, <code>list_projects</code>, <code>get_project</code>,
          <code>create_project</code>, <code>update_project</code>, <code>list_buildings</code>,
          <code>create_building</code>, <code>update_building</code>, <code>set_floors</code>,
          <code>get_floor_proposal</code>, <code>accept_floor_proposal_blocks</code>,
          <code>list_site_features</code>, <code>create_site_feature</code>. Deleting, documents,
          mapping and prices stay in this app. Every change lands in the audit log with the token
          prefix as its request id.
        </p>
        <p class="uf-hint">
          Known gap: tokens are bearer secrets sent on every call, not an OAuth sign-in; keep them
          where you keep passwords, give each device its own, and revoke what you stop using.
        </p>
      </uf-section-card>
    </div>
  `,
  styles: `
    .actions {
      text-align: right;
      white-space: nowrap;
    }
    .dim td {
      color: var(--uf-muted);
    }
    .connect {
      margin: 0;
      display: grid;
      gap: 0.75rem;
    }
    .connect dt {
      font-weight: 600;
      margin-bottom: 0.2rem;
    }
    .connect dd {
      margin: 0;
    }
    .connect pre {
      margin: 0;
      white-space: pre-wrap;
      word-break: break-all;
    }
    .row {
      display: flex;
      align-items: center;
      gap: 0.5rem;
      flex-wrap: wrap;
    }
    .row code {
      word-break: break-all;
      user-select: all;
    }
    .secret .row {
      display: flex;
      align-items: center;
      gap: 0.5rem;
      flex-wrap: wrap;
      margin: 0.35rem 0;
    }
    .secret code {
      word-break: break-all;
      user-select: all;
    }
    button ng-icon {
      vertical-align: -0.15em;
      margin-right: 0.25rem;
    }
  `,
})
export class TokensPage {
  private readonly api = inject(UnitformaApi);
  private readonly dialogs = inject(DialogsService);
  private readonly toast = inject(ToastService);
  private readonly session = inject(SessionStore);
  readonly tenantId = input.required<string>();
  readonly tokens = signal<ApiTokenOut[]>([]);
  readonly created = signal<ApiTokenCreated | null>(null);
  readonly busy = signal(false);
  readonly error = signal<string | null>(null);
  readonly scopes = SCOPES;
  readonly expiries = EXPIRIES;
  readonly me = computed(() => this.session.me()?.email ?? 'you');
  readonly activeCount = computed(() => this.tokens().filter((t) => t.status === 'active').length);
  readonly facts = computed<HeaderFact[]>(() => [
    { label: 'Tokens', value: this.tokens().length },
    { domain: 'token', status: 'active', value: `${this.activeCount()} active` },
  ]);
  name = '';
  scope: Scope = 'read';
  days = 90;
  day = dayOf;
  since = ago;

  constructor() {
    toObservable(this.tenantId).subscribe(() => void this.load());
  }

  scopeHelp(): string {
    const s = SCOPES.find((x) => x.value === this.scope);
    return s ? `${s.label}: ${s.does}` : '';
  }

  mcpUrl(): string {
    return `${location.origin}/mcp`;
  }

  /** The secret of the token just created, else a placeholder the reader replaces. */
  tokenText(): string {
    return this.created()?.secret ?? '<paste your token>';
  }

  claudeCommand(): string {
    return `claude mcp add --transport http unitforma ${this.mcpUrl()} --header "Authorization: Bearer ${this.tokenText()}"`;
  }

  mcpJson(): string {
    const token = this.created()?.secret ?? '${UNITFORMA_TOKEN}';
    return JSON.stringify(
      {
        mcpServers: {
          unitforma: {
            type: 'http',
            url: this.mcpUrl(),
            headers: { Authorization: `Bearer ${token}` },
          },
        },
      },
      null,
      2,
    );
  }

  curlCommand(): string {
    return `curl -sS ${this.mcpUrl()} -H "Authorization: Bearer ${this.tokenText()}" -H "Accept: application/json, text/event-stream" -H "Content-Type: application/json" -d '{"jsonrpc":"2.0","id":1,"method":"tools/list"}'`;
  }

  async load(): Promise<void> {
    try {
      this.tokens.set(await this.api.listApiTokens(this.tenantId()));
    } catch (e) {
      this.error.set(problemMessage(e));
    }
  }

  create(): Promise<void> {
    if (!this.name.trim()) return Promise.resolve();
    return this.run(async () => {
      const c = await this.api.createApiToken(this.tenantId(), {
        name: this.name.trim(),
        scope: this.scope,
        expires_in_days: this.days,
      });
      this.created.set(c);
      this.toast.ok(`Token "${c.name}" created; copy the secret now`);
      this.name = '';
    });
  }

  async copy(text: string, done: string): Promise<void> {
    try {
      await navigator.clipboard.writeText(text);
      this.toast.ok(done);
    } catch {
      this.error.set('Clipboard unavailable: select the text and copy it yourself.');
    }
  }

  async revoke(t: ApiTokenOut): Promise<void> {
    const ok = await this.dialogs.confirm({
      title: `Revoke "${t.name}"?`,
      message: `The token ${t.token_prefix}… stops working on its next call.`,
      consequence: 'Create a new token if the assistant should keep working.',
      confirmLabel: 'Revoke',
      tone: 'bad',
    });
    if (!ok) return;
    return this.run(async () => {
      await this.api.revokeApiToken(this.tenantId(), t.id);
      if (this.created()?.id === t.id) this.created.set(null);
      this.toast.ok(`Token "${t.name}" revoked`);
    });
  }

  private async run(fn: () => Promise<unknown>): Promise<void> {
    this.busy.set(true);
    this.error.set(null);
    try {
      await fn();
      await this.load();
    } catch (e) {
      this.error.set(problemMessage(e));
    } finally {
      this.busy.set(false);
    }
  }
}

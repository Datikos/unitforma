import { ChangeDetectionStrategy, Component, computed, input } from '@angular/core';
import { RouterLink } from '@angular/router';
import { NgIcon, provideIcons } from '@ng-icons/core';
import { PageHeaderComponent, UF_ICONS } from 'ui';
import { GUIDE, GUIDE_ORDER, GuideKey, PROJECT_FLOW } from './guide-content';
import { GuideEntryComponent } from './guide-entry.component';

/** The whole manual: how a project flows, then one entry per screen. */
@Component({
  selector: 'uf-guide-page',
  imports: [RouterLink, NgIcon, PageHeaderComponent, GuideEntryComponent],
  viewProviders: [provideIcons(UF_ICONS)],
  changeDetection: ChangeDetectionStrategy.OnPush,
  template: `
    <div class="uf-page">
      <uf-page-header title="Guide" icon="lucideBookOpen" kicker="How Unitforma works">
        <p subtitle class="uf-muted">
          A developer uploads what it has, a reviewer turns drawings into verified units, sales adds
          prices, and the project is published as a buyer portal. Each screen below explains its
          controls and who may use them.
        </p>
      </uf-page-header>

      <section class="flow uf-card">
        <h2 class="flow__title">The way through a project</h2>
        <ol class="flow__steps">
          @for (s of flow; track s.key; let last = $last) {
            <li>
              <a [routerLink]="['/guide', s.key]" class="flow__step"
                ><ng-icon [name]="s.icon" aria-hidden="true" /><span>{{ s.label }}</span></a
              >
              @if (!last) {
                <ng-icon name="lucideArrowRight" class="flow__arrow" aria-hidden="true" />
              }
            </li>
          }
          <li>
            <span class="flow__step flow__step--portal"
              ><ng-icon name="lucideGlobe" aria-hidden="true" /><span>Buyer portal</span></span
            >
          </li>
        </ol>
        <p class="uf-hint">
          Documents feed sheets; approved sheets create units; units get prices; a publication
          snapshot is what buyers see. Later drawing revisions go through a revision diff so unit
          identities, prices and leads survive.
        </p>
      </section>

      <div class="layout">
        <nav class="toc" aria-label="Guide contents">
          @for (k of keys; track k) {
            <a [routerLink]="['/guide', k]" [class.is-active]="k === active()"
              ><ng-icon [name]="GUIDE[k].icon" aria-hidden="true" />{{ GUIDE[k].title }}</a
            >
          }
        </nav>
        <div class="entries">
          @for (k of visible(); track k) {
            <section class="uf-card" [id]="k"><uf-guide-entry [entry]="GUIDE[k]" /></section>
          }
        </div>
      </div>
    </div>
  `,
  styles: `
    .flow__title {
      margin: 0 0 0.75rem;
      font-size: 1rem;
    }
    .flow__steps {
      display: flex;
      flex-wrap: wrap;
      align-items: center;
      gap: 0.35rem;
      margin: 0;
      padding: 0;
      list-style: none;
    }
    .flow__steps li {
      display: inline-flex;
      align-items: center;
      gap: 0.35rem;
    }
    .flow__step {
      display: inline-flex;
      align-items: center;
      gap: 0.4rem;
      padding: 0.45rem 0.8rem;
      border-radius: var(--uf-radius-pill);
      border: 1px solid var(--uf-border-strong);
      background: var(--uf-surface);
      color: var(--uf-text);
      text-decoration: none;
      font-weight: 600;
      font-size: 0.9rem;
    }
    .flow__step ng-icon {
      color: var(--uf-primary);
    }
    .flow__step--portal {
      border-color: var(--uf-tone-good-border);
      background: var(--uf-tone-good-bg);
    }
    .flow__step--portal ng-icon {
      color: var(--uf-tone-good-fg);
    }
    .flow__arrow {
      color: var(--uf-muted);
    }
    .layout {
      display: grid;
      grid-template-columns: 240px 1fr;
      gap: 1rem;
      align-items: start;
    }
    .toc {
      position: sticky;
      top: calc(var(--uf-topbar-height) + 1rem);
      display: grid;
      gap: 0.1rem;
    }
    .toc a {
      display: flex;
      align-items: center;
      gap: 0.5rem;
      padding: 0.4rem 0.6rem;
      border-radius: var(--uf-radius-sm);
      color: var(--uf-text);
      text-decoration: none;
      font-size: 0.9rem;
    }
    .toc a:hover,
    .toc a.is-active {
      background: var(--uf-primary-soft);
      color: var(--uf-primary-strong);
    }
    .entries {
      display: grid;
      gap: 1rem;
      min-width: 0;
    }
    @media (max-width: 900px) {
      .layout {
        grid-template-columns: 1fr;
      }
      .toc {
        position: static;
        grid-template-columns: repeat(auto-fill, minmax(12rem, 1fr));
      }
    }
  `,
})
export class GuidePage {
  readonly key = input<string | undefined>();
  readonly GUIDE = GUIDE;
  readonly keys = GUIDE_ORDER;
  readonly flow = PROJECT_FLOW;
  readonly active = computed(() =>
    this.key() && this.key()! in GUIDE ? (this.key() as GuideKey) : null,
  );
  readonly visible = computed(() => (this.active() ? [this.active()!] : [...GUIDE_ORDER]));
}

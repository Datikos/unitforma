import { ChangeDetectionStrategy, Component, input } from '@angular/core';
import { RouterLink } from '@angular/router';
import { NgIcon, provideIcons } from '@ng-icons/core';
import { UF_ICONS } from './icons';

export interface Crumb {
  label: string;
  link?: unknown[] | string | null;
  icon?: string;
}

@Component({
  selector: 'uf-breadcrumbs',
  imports: [RouterLink, NgIcon],
  viewProviders: [provideIcons(UF_ICONS)],
  changeDetection: ChangeDetectionStrategy.OnPush,
  template: `
    <nav class="bc" aria-label="Breadcrumb">
      <ol>
        @for (c of items(); track $index; let last = $last) {
          <li>
            @if (c.link && !last) {
              <a [routerLink]="c.link">
                @if (c.icon) {
                  <ng-icon [name]="c.icon" aria-hidden="true" />
                }
                {{ c.label }}</a
              >
            } @else {
              <span [attr.aria-current]="last ? 'page' : null">
                @if (c.icon) {
                  <ng-icon [name]="c.icon" aria-hidden="true" />
                }
                {{ c.label }}</span
              >
            }
            @if (!last) {
              <ng-icon name="lucideChevronRight" class="bc__sep" aria-hidden="true" />
            }
          </li>
        }
      </ol>
    </nav>
  `,
  styles: `
    .bc ol {
      display: flex;
      flex-wrap: wrap;
      align-items: center;
      gap: 0.15rem;
      margin: 0;
      padding: 0;
      list-style: none;
      font-size: 0.85rem;
      color: var(--uf-muted);
    }
    .bc li {
      display: inline-flex;
      align-items: center;
      gap: 0.15rem;
      min-width: 0;
    }
    .bc a,
    .bc span {
      display: inline-flex;
      align-items: center;
      gap: 0.3rem;
      color: inherit;
      text-decoration: none;
      padding: 0.1rem 0.35rem;
      border-radius: 6px;
      max-width: 28ch;
      overflow: hidden;
      text-overflow: ellipsis;
      white-space: nowrap;
    }
    .bc a:hover {
      background: var(--uf-surface-2);
      color: var(--uf-text);
    }
    .bc span[aria-current] {
      color: var(--uf-text);
      font-weight: 600;
    }
    .bc__sep {
      opacity: 0.6;
    }
  `,
})
export class BreadcrumbsComponent {
  readonly items = input.required<Crumb[]>();
}

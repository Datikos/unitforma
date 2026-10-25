import { TestBed } from '@angular/core/testing';
import { MatDialog } from '@angular/material/dialog';
import { of } from 'rxjs';
import { DialogsService } from './dialogs.service';

describe('DialogsService', () => {
  function withResult(result: unknown): DialogsService {
    TestBed.configureTestingModule({
      providers: [
        { provide: MatDialog, useValue: { open: () => ({ afterClosed: () => of(result) }) } },
      ],
    });
    return TestBed.inject(DialogsService);
  }

  it('confirm resolves true only when the dialog closes with true', async () => {
    expect(await withResult(true).confirm({ title: 'x', message: 'y' })).toBe(true);
    TestBed.resetTestingModule();
    expect(await withResult(undefined).confirm({ title: 'x', message: 'y' })).toBe(false);
  });

  it('prompt resolves the typed value and null when dismissed', async () => {
    expect(await withResult('A-12').prompt({ title: 'x', label: 'Code' })).toBe('A-12');
    TestBed.resetTestingModule();
    expect(await withResult(undefined).prompt({ title: 'x', label: 'Code' })).toBeNull();
  });
});

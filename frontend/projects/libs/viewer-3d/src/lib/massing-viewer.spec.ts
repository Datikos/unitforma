import { TestBed } from '@angular/core/testing';
import { MassingViewerComponent } from './massing-viewer';

describe('MassingViewerComponent', () => {
  it('reports when WebGL is unavailable instead of throwing (fallback ladder, plan §11.3)', async () => {
    await TestBed.configureTestingModule({ imports: [MassingViewerComponent] }).compileComponents();
    const fixture = TestBed.createComponent(MassingViewerComponent);
    fixture.componentRef.setInput('src', 'https://example.invalid/massing.glb');
    await fixture.whenStable();
    fixture.detectChanges();
    // jsdom has no WebGL context: the component must degrade to a status message
    expect(fixture.componentInstance.status()).toContain('WebGL');
  });
});

import { ComponentFixture, TestBed } from '@angular/core/testing';
import { PlanViewer } from './plan-viewer';

describe('PlanViewer', () => {
  let component: PlanViewer;
  let fixture: ComponentFixture<PlanViewer>;

  beforeEach(async () => {
    await TestBed.configureTestingModule({
      imports: [PlanViewer],
    }).compileComponents();

    fixture = TestBed.createComponent(PlanViewer);
    component = fixture.componentInstance;
    await fixture.whenStable();
  });

  it('should create', () => {
    expect(component).toBeTruthy();
  });
});

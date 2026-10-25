import { ComponentFixture, TestBed } from '@angular/core/testing';
import { DomainModels } from './domain-models';

describe('DomainModels', () => {
  let component: DomainModels;
  let fixture: ComponentFixture<DomainModels>;

  beforeEach(async () => {
    await TestBed.configureTestingModule({
      imports: [DomainModels],
    }).compileComponents();

    fixture = TestBed.createComponent(DomainModels);
    component = fixture.componentInstance;
    await fixture.whenStable();
  });

  it('should create', () => {
    expect(component).toBeTruthy();
  });
});

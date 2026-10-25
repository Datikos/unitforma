import { ComponentFixture, TestBed } from '@angular/core/testing';
import { ApiClient } from './api-client';

describe('ApiClient', () => {
  let component: ApiClient;
  let fixture: ComponentFixture<ApiClient>;

  beforeEach(async () => {
    await TestBed.configureTestingModule({
      imports: [ApiClient],
    }).compileComponents();

    fixture = TestBed.createComponent(ApiClient);
    component = fixture.componentInstance;
    await fixture.whenStable();
  });

  it('should create', () => {
    expect(component).toBeTruthy();
  });
});

import { ComponentFixture, TestBed } from '@angular/core/testing';
import { AuthBuyer } from './auth-buyer';

describe('AuthBuyer', () => {
  let component: AuthBuyer;
  let fixture: ComponentFixture<AuthBuyer>;

  beforeEach(async () => {
    await TestBed.configureTestingModule({
      imports: [AuthBuyer],
    }).compileComponents();

    fixture = TestBed.createComponent(AuthBuyer);
    component = fixture.componentInstance;
    await fixture.whenStable();
  });

  it('should create', () => {
    expect(component).toBeTruthy();
  });
});

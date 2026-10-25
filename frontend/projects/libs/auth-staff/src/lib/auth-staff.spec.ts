import { ComponentFixture, TestBed } from '@angular/core/testing';
import { AuthStaff } from './auth-staff';

describe('AuthStaff', () => {
  let component: AuthStaff;
  let fixture: ComponentFixture<AuthStaff>;

  beforeEach(async () => {
    await TestBed.configureTestingModule({
      imports: [AuthStaff],
    }).compileComponents();

    fixture = TestBed.createComponent(AuthStaff);
    component = fixture.componentInstance;
    await fixture.whenStable();
  });

  it('should create', () => {
    expect(component).toBeTruthy();
  });
});

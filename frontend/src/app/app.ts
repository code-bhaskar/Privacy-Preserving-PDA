import { Component, computed, inject, signal } from '@angular/core';
import { AuthService } from './services/auth.service';
import { Login } from './components/login';
import { Shell } from './components/shell';

@Component({
  selector: 'app-root',
  imports: [Login, Shell],
  template: `
    @if (auth.isAuthenticated()) {
      <app-shell />
    } @else {
      <app-login />
    }
  `,
})
export class App {
  protected readonly auth = inject(AuthService);
  protected readonly ready = computed(() => this.auth.isAuthenticated());
}

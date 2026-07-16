import { describe, it, expect, beforeAll, afterAll } from 'vitest';
import { render } from '@testing-library/react';
import App from '../App';

describe('App', () => {
  beforeAll(() => {
    // Mock fetch to return 401 for auth check
    window.fetch = async () =>
      new Response(JSON.stringify({ detail: 'unauthorized' }), { status: 401 });
  });
  afterAll(() => {
    delete (window as any).fetch;
  });

  it('renders without crashing', () => {
    const { container } = render(<App />);
    expect(container).toBeTruthy();
  });
});
import { describe, it, expect } from 'vitest';
import { render, screen } from '@testing-library/react';
import { CheckBadge } from '../CheckBadge';

describe('CheckBadge', () => {
  it('renders success check with green icon', () => {
    const { container } = render(<CheckBadge name="build" status="success" />);
    expect(screen.getByText(/build/)).toBeInTheDocument();
    const el = container.firstChild as HTMLElement;
    expect(el.className).toContain('text-green');
  });

  it('renders failure check with red icon', () => {
    const { container } = render(<CheckBadge name="lint" status="failure" />);
    expect(screen.getByText(/lint/)).toBeInTheDocument();
    const el = container.firstChild as HTMLElement;
    expect(el.className).toContain('text-red');
  });

  it('renders pending check with yellow icon', () => {
    const { container } = render(<CheckBadge name="deploy" status="pending" />);
    expect(screen.getByText(/deploy/)).toBeInTheDocument();
    const el = container.firstChild as HTMLElement;
    expect(el.className).toContain('text-yellow');
  });

  it('shows duration when provided', () => {
    render(<CheckBadge name="build" status="success" duration="3m" />);
    expect(screen.getByText(/build \(3m\)/)).toBeInTheDocument();
  });

  it('does not show duration when not provided', () => {
    render(<CheckBadge name="build" status="success" />);
    expect(screen.queryByText(/\(/)).toBeNull();
  });
});
import { describe, it, expect } from 'vitest';
import { render, screen } from '@testing-library/react';
import { RoleBadge } from '../RoleBadge';

describe('RoleBadge', () => {
  it('renders role text with underscores replaced', () => {
    render(<RoleBadge role="super_admin" />);
    expect(screen.getByText('super admin')).toBeInTheDocument();
  });

  it('applies indigo color for super_admin', () => {
    const { container } = render(<RoleBadge role="super_admin" />);
    const badge = container.firstChild as HTMLElement;
    expect(badge.className).toContain('indigo');
  });

  it('applies indigo color for project_admin', () => {
    const { container } = render(<RoleBadge role="project_admin" />);
    const badge = container.firstChild as HTMLElement;
    expect(badge.className).toContain('indigo');
  });

  it('applies green color for maintainer', () => {
    const { container } = render(<RoleBadge role="maintainer" />);
    const badge = container.firstChild as HTMLElement;
    expect(badge.className).toContain('green');
  });

  it('applies blue color for developer', () => {
    const { container } = render(<RoleBadge role="developer" />);
    const badge = container.firstChild as HTMLElement;
    expect(badge.className).toContain('blue');
  });

  it('applies gray color for viewer', () => {
    const { container } = render(<RoleBadge role="viewer" />);
    const badge = container.firstChild as HTMLElement;
    expect(badge.className).toContain('gray');
  });

  it('uses accent color for unknown roles', () => {
    const { container } = render(<RoleBadge role="lead_engineer" />);
    const badge = container.firstChild as HTMLElement;
    expect(badge.className).toContain('[#6366f1]');
  });
});
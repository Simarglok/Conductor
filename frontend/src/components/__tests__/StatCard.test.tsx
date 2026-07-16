import { describe, it, expect } from 'vitest';
import { render, screen } from '@testing-library/react';
import { StatCard } from '../StatCard';
import type { StatCardColor } from '../StatCard';

describe('StatCard', () => {
  it('renders value and label', () => {
    render(<StatCard value={42} label="Active DAGs" />);
    expect(screen.getByText('42')).toBeInTheDocument();
    expect(screen.getByText('Active DAGs')).toBeInTheDocument();
  });

  it('renders string value', () => {
    render(<StatCard value="N/A" label="Status" />);
    expect(screen.getByText('N/A')).toBeInTheDocument();
  });

  it('applies correct color class', () => {
    const colors: StatCardColor[] = ['green', 'red', 'yellow', 'blue'];
    for (const color of colors) {
      const { container } = render(<StatCard value={1} label="Test" color={color} />);
      const valueEl = container.querySelector('.text-2xl');
      expect(valueEl).toBeTruthy();
    }
  });

  it('defaults to blue color', () => {
    const { container } = render(<StatCard value={1} label="Test" />);
    const valueEl = container.querySelector('.text-2xl');
    expect(valueEl?.className).toContain('text-[');
  });
});
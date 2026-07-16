import { describe, it, expect } from 'vitest';
import { render, screen } from '@testing-library/react';
import { BranchInfoBar } from '../BranchInfoBar';

describe('BranchInfoBar', () => {
  it('renders branch name', () => {
    render(<BranchInfoBar branch="feature/new-model" />);
    expect(screen.getByText('feature/new-model')).toBeInTheDocument();
  });

  it('shows ahead indicator when ahead > 0', () => {
    render(<BranchInfoBar branch="feature/x" ahead={3} />);
    expect(screen.getByText('↑ 3 ahead of main')).toBeInTheDocument();
  });

  it('does not show ahead when ahead is 0', () => {
    render(<BranchInfoBar branch="feature/x" ahead={0} />);
    expect(screen.queryByText(/ahead/)).toBeNull();
  });

  it('shows behind indicator when behind > 0', () => {
    render(<BranchInfoBar branch="feature/x" behind={2} />);
    expect(screen.getByText('↓ 2 behind main')).toBeInTheDocument();
  });

  it('renders children', () => {
    render(
      <BranchInfoBar branch="main">
        <button>Sync</button>
      </BranchInfoBar>
    );
    expect(screen.getByText('Sync')).toBeInTheDocument();
  });

  it('renders Active label', () => {
    render(<BranchInfoBar branch="main" />);
    expect(screen.getByText('Active:')).toBeInTheDocument();
  });
});
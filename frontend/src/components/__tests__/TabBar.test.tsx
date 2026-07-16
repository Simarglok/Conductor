import { describe, it, expect, vi } from 'vitest';
import { render, screen, fireEvent } from '@testing-library/react';
import { TabBar } from '../TabBar';

describe('TabBar', () => {
  const tabs = [
    { id: 'dags', label: 'DAGs Overview' },
    { id: 'runs', label: 'Recent Runs' },
    { id: 'schedule', label: 'Schedule' },
  ];

  it('renders all tabs', () => {
    render(<TabBar tabs={tabs} active="dags" onChange={() => {}} />);
    expect(screen.getByText('DAGs Overview')).toBeInTheDocument();
    expect(screen.getByText('Recent Runs')).toBeInTheDocument();
    expect(screen.getByText('Schedule')).toBeInTheDocument();
  });

  it('highlights active tab', () => {
    render(<TabBar tabs={tabs} active="runs" onChange={() => {}} />);
    const activeTab = screen.getByText('Recent Runs');
    expect(activeTab.className).toContain('text-white');
    expect(activeTab.className).toContain('border-[#6366f1]');
  });

  it('fires onChange on click', () => {
    const onChange = vi.fn();
    render(<TabBar tabs={tabs} active="dags" onChange={onChange} />);
    fireEvent.click(screen.getByText('Schedule'));
    expect(onChange).toHaveBeenCalledWith('schedule');
  });

  it('renders rightAction', () => {
    render(
      <TabBar
        tabs={tabs}
        active="dags"
        onChange={() => {}}
        rightAction={<span>Action</span>}
      />
    );
    expect(screen.getByText('Action')).toBeInTheDocument();
  });
});
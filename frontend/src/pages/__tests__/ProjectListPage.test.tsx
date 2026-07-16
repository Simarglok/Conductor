import { describe, it, expect, vi, beforeAll, afterAll } from 'vitest';
import { render, screen, fireEvent, waitFor } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
import ProjectListPage from '../../pages/ProjectListPage';

const mockProjects = [
  { id: '1', name: 'Data Warehouse', slug: 'data-warehouse', description: 'Main DW', member_count: 5, role: 'super_admin', created_at: '2026-01-01' },
  { id: '2', name: 'Marketing', slug: 'marketing', description: null, member_count: 3, role: 'developer', created_at: '2026-02-01' },
];

describe('ProjectListPage', () => {
  beforeAll(() => {
    window.fetch = vi.fn().mockResolvedValue({
      ok: true,
      status: 200,
      json: () => Promise.resolve(mockProjects),
    });
  });

  afterAll(() => {
    delete (window as any).fetch;
  });

  it('renders project cards after loading', async () => {
    render(
      <MemoryRouter>
        <ProjectListPage />
      </MemoryRouter>
    );
    await waitFor(() => {
      expect(screen.getByText('Data Warehouse')).toBeInTheDocument();
      expect(screen.getByText('Marketing')).toBeInTheDocument();
    });
  });

  it('shows member count', async () => {
    render(
      <MemoryRouter>
        <ProjectListPage />
      </MemoryRouter>
    );
    await waitFor(() => {
      expect(screen.getByText('5 members')).toBeInTheDocument();
      expect(screen.getByText('3 members')).toBeInTheDocument();
    });
  });

  it('shows role badges', async () => {
    render(
      <MemoryRouter>
        <ProjectListPage />
      </MemoryRouter>
    );
    await waitFor(() => {
      expect(screen.getByText('super admin')).toBeInTheDocument();
      expect(screen.getByText('developer')).toBeInTheDocument();
    });
  });

  it('shows "+ New Project" button', async () => {
    render(
      <MemoryRouter>
        <ProjectListPage />
      </MemoryRouter>
    );
    await waitFor(() => {
      expect(screen.getByText('+ New Project')).toBeInTheDocument();
    });
  });

  it('opens create modal on "+ New Project" click', async () => {
    render(
      <MemoryRouter>
        <ProjectListPage />
      </MemoryRouter>
    );
    await waitFor(() => {
      expect(screen.getByText('Data Warehouse')).toBeInTheDocument();
    });
    fireEvent.click(screen.getByText('+ New Project'));
    expect(screen.getByText('New Project')).toBeInTheDocument();
    expect(screen.getByPlaceholderText('My Project')).toBeInTheDocument();
  });
});
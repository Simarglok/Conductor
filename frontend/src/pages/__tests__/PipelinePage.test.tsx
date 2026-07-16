import { describe, it, expect, vi, beforeAll, afterAll } from 'vitest';
import { render, screen, waitFor } from '@testing-library/react';
import { MemoryRouter, Route, Routes } from 'react-router-dom';
import PipelinePage from '../../pages/PipelinePage';

const mockStats = {
  active_dags: 5,
  paused_dags: 2,
  running: 3,
  queued: 1,
  runs_today: 12,
  failed_24h: 2,
};

const mockDags = [
  { dag_id: 'etl_main', description: 'Main ETL', is_paused: false },
  { dag_id: 'cleanup', description: null, is_paused: true },
];

const mockRuns = [
  {
    run_id: 'run_1',
    state: 'success',
    execution_date: '2026-07-15T00:00:00Z',
    start_date: null,
    end_date: null,
  },
  {
    run_id: 'run_2',
    state: 'failed',
    execution_date: '2026-07-14T00:00:00Z',
    start_date: null,
    end_date: null,
  },
];

describe('PipelinePage', () => {
  beforeAll(() => {
    window.fetch = vi.fn((url: string) => {
      const urlStr = String(url);
      if (urlStr.includes('/stats')) {
        return Promise.resolve({ ok: true, status: 200, json: () => Promise.resolve(mockStats) });
      }
      if (urlStr.includes('/runs')) {
        return Promise.resolve({ ok: true, status: 200, json: () => Promise.resolve(mockRuns) });
      }
      return Promise.resolve({ ok: true, status: 200, json: () => Promise.resolve(mockDags) });
    });
  });

  afterAll(() => {
    delete (window as any).fetch;
  });

  it('renders stat cards with API data', async () => {
    render(
      <MemoryRouter initialEntries={['/projects/test/pipeline']}>
        <Routes>
          <Route path="/projects/:slug/pipeline" element={<PipelinePage />} />
        </Routes>
      </MemoryRouter>
    );
    await waitFor(() => {
      expect(screen.getByText('5')).toBeInTheDocument();
      expect(screen.getByText('Active DAGs')).toBeInTheDocument();
      expect(screen.getByText('Running')).toBeInTheDocument();
      expect(screen.getByText('Queued')).toBeInTheDocument();
      expect(screen.getByText('Runs Today')).toBeInTheDocument();
      expect(screen.getByText('Failed (24h)')).toBeInTheDocument();
    });
  });

  it('renders DAG list items', async () => {
    render(
      <MemoryRouter initialEntries={['/projects/test/pipeline']}>
        <Routes>
          <Route path="/projects/:slug/pipeline" element={<PipelinePage />} />
        </Routes>
      </MemoryRouter>
    );
    await waitFor(() => {
      expect(screen.getByText('etl_main')).toBeInTheDocument();
      expect(screen.getByText('cleanup')).toBeInTheDocument();
    });
  });

  it('shows DAG status badges', async () => {
    render(
      <MemoryRouter initialEntries={['/projects/test/pipeline']}>
        <Routes>
          <Route path="/projects/:slug/pipeline" element={<PipelinePage />} />
        </Routes>
      </MemoryRouter>
    );
    await waitFor(() => {
      expect(screen.getByText('ACTIVE')).toBeInTheDocument();
      expect(screen.getByText('PAUSED')).toBeInTheDocument();
    });
  });

  it('renders tabs', async () => {
    render(
      <MemoryRouter initialEntries={['/projects/test/pipeline']}>
        <Routes>
          <Route path="/projects/:slug/pipeline" element={<PipelinePage />} />
        </Routes>
      </MemoryRouter>
    );
    await waitFor(() => {
      expect(screen.getByText('DAGs Overview')).toBeInTheDocument();
      expect(screen.getByText('Recent Runs')).toBeInTheDocument();
      expect(screen.getByText('Schedule')).toBeInTheDocument();
    });
  });

  it('shows "Open in Airflow" link', async () => {
    render(
      <MemoryRouter initialEntries={['/projects/test/pipeline']}>
        <Routes>
          <Route path="/projects/:slug/pipeline" element={<PipelinePage />} />
        </Routes>
      </MemoryRouter>
    );
    await waitFor(() => {
      const link = screen.getByText(/Open in Airflow/);
      expect(link).toBeInTheDocument();
      expect(link).toHaveAttribute('target', '_blank');
    });
  });
});
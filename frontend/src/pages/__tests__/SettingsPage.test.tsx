import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import { render, screen, fireEvent, waitFor } from '@testing-library/react';
import { MemoryRouter, Route, Routes } from 'react-router-dom';
import SettingsPage from '../SettingsPage';

const mockGit = {
  repo_url: 'https://github.com/org/repo',
  default_branch: 'main',
  dbt_path: 'dbt/',
  dags_path: 'dags/',
  auth_type: 'https',
};

const mockSettings = { self_approve_enabled: false };

const mockMembers = [
  { user_id: '1', email: 'dev@test.com', role_name: 'developer' },
];

const mockEnvs = [
  { id: 'e1', name: 'production', branch_name: 'main', is_protected: true },
];

function createFetchMock() {
  return vi.fn((url: string, options?: RequestInit) => {
    const urlStr = url.toString();

    if (urlStr.includes('/projects/test-slug/git') && (!options || options.method === undefined || options.method === 'GET')) {
      return Promise.resolve({
        ok: true,
        status: 200,
        json: () => Promise.resolve(mockGit),
      });
    }
    if (urlStr.includes('/projects/test-slug/settings') && (!options || options.method === 'PATCH' || options.method === undefined || options.method === 'GET')) {
      return Promise.resolve({
        ok: true,
        status: 200,
        json: () => Promise.resolve(mockSettings),
      });
    }
    if (urlStr.includes('/projects/test-slug/members') && (!options || options.method === undefined || options.method === 'GET')) {
      return Promise.resolve({
        ok: true,
        status: 200,
        json: () => Promise.resolve(mockMembers),
      });
    }
    if (urlStr.includes('/projects/test-slug/environments') && (!options || options.method === undefined || options.method === 'GET')) {
      return Promise.resolve({
        ok: true,
        status: 200,
        json: () => Promise.resolve(mockEnvs),
      });
    }
    // For PATCH settings (toggle self-approve)
    if (urlStr.includes('/projects/test-slug/settings') && options?.method === 'PATCH') {
      return Promise.resolve({
        ok: true,
        status: 200,
        json: () => Promise.resolve({ self_approve_enabled: true }),
      });
    }
    // For PUT git
    if (urlStr.includes('/projects/test-slug/git') && options?.method === 'PUT') {
      return Promise.resolve({
        ok: true,
        status: 200,
        json: () => Promise.resolve({ ...mockGit }),
      });
    }
    // For POST members
    if (urlStr.includes('/projects/test-slug/members') && options?.method === 'POST') {
      return Promise.resolve({
        ok: true,
        status: 200,
        json: () => Promise.resolve({ user_id: '2', email: 'new@test.com', role_name: 'developer' }),
      });
    }
    // For DELETE members
    if (urlStr.includes('/projects/test-slug/members/') && options?.method === 'DELETE') {
      return Promise.resolve({ ok: true, status: 204, json: () => Promise.resolve(null) });
    }
    // For POST environments
    if (urlStr.includes('/projects/test-slug/environments') && options?.method === 'POST') {
      return Promise.resolve({
        ok: true,
        status: 200,
        json: () => Promise.resolve({ id: 'e2', name: 'staging', branch_name: 'develop', is_protected: false }),
      });
    }
    // For DELETE environments
    if (urlStr.includes('/projects/test-slug/environments/') && options?.method === 'DELETE') {
      return Promise.resolve({ ok: true, status: 204, json: () => Promise.resolve(null) });
    }

    return Promise.resolve({ ok: true, status: 200, json: () => Promise.resolve(null) });
  });
}

function renderSettingsPage() {
  return render(
    <MemoryRouter initialEntries={['/projects/test-slug/settings']}>
      <Routes>
        <Route path="/projects/:slug/settings" element={<SettingsPage />} />
      </Routes>
    </MemoryRouter>
  );
}

describe('SettingsPage', () => {
  beforeEach(() => {
    window.fetch = createFetchMock() as any;
  });

  afterEach(() => {
    delete (window as any).fetch;
  });

  it('renders 4 tabs with correct labels', async () => {
    renderSettingsPage();
    await waitFor(() => {
      expect(screen.getByText('Git & Repository')).toBeInTheDocument();
      expect(screen.getByText('Environments')).toBeInTheDocument();
      expect(screen.getByText('Members (1)')).toBeInTheDocument();
      expect(screen.getByText('Feature Toggles')).toBeInTheDocument();
    });
  });

  it('shows git config in read-only mode by default', async () => {
    renderSettingsPage();
    await waitFor(() => {
      expect(screen.getByText('https://github.com/org/repo')).toBeInTheDocument();
      expect(screen.getByText('main')).toBeInTheDocument();
      expect(screen.getByText('dbt/')).toBeInTheDocument();
      expect(screen.getByText('dags/')).toBeInTheDocument();
    });
  });

  it('shows inline edit form when Edit Config is clicked', async () => {
    renderSettingsPage();
    await waitFor(() => {
      expect(screen.getByText('https://github.com/org/repo')).toBeInTheDocument();
    });

    fireEvent.click(screen.getByText('Edit Config'));

    // Should now show input fields and Save/Cancel buttons
    expect(screen.getByText('Repository URL')).toBeInTheDocument();
    expect(screen.getByText('Auth Type')).toBeInTheDocument();
    expect(screen.getByText('Default Branch')).toBeInTheDocument();
    expect(screen.getByText('dbt Path')).toBeInTheDocument();
    expect(screen.getByText('DAGs Path')).toBeInTheDocument();
    expect(screen.getByText('Save')).toBeInTheDocument();
    expect(screen.getByText('Cancel')).toBeInTheDocument();

    // The repository URL input should have the current value
    const urlInput = screen.getByDisplayValue('https://github.com/org/repo');
    expect(urlInput).toBeInTheDocument();
  });

  it('sends a Git access token only when token auth is selected', async () => {
    renderSettingsPage();
    await waitFor(() => {
      expect(screen.getByText('Edit Config')).toBeInTheDocument();
    });

    fireEvent.click(screen.getByText('Edit Config'));
    fireEvent.change(screen.getByDisplayValue('HTTPS'), { target: { value: 'token' } });

    const tokenInput = screen.getByLabelText('Access Token');
    expect(tokenInput).toHaveAttribute('type', 'password');
    fireEvent.change(tokenInput, { target: { value: 'github_pat_secret' } });
    fireEvent.click(screen.getByText('Save'));

    await waitFor(() => {
      const putCall = (window.fetch as any).mock.calls.find(
        ([url, options]: [string, RequestInit]) =>
          url.includes('/projects/test-slug/git') && options?.method === 'PUT'
      );
      expect(putCall).toBeTruthy();
      expect(JSON.parse(putCall[1].body)).toMatchObject({
        auth_type: 'token',
        token: 'github_pat_secret',
      });
    });
  });

  it('switches to Environments tab and shows environment data', async () => {
    renderSettingsPage();
    await waitFor(() => {
      expect(screen.getByText('Environments')).toBeInTheDocument();
    });

    fireEvent.click(screen.getByText('Environments'));

    await waitFor(() => {
      expect(screen.getByText('production')).toBeInTheDocument();
      expect(screen.getByText('main')).toBeInTheDocument();
    });
  });

  it('toggles from read-only to edit and back on Cancel', async () => {
    renderSettingsPage();
    await waitFor(() => {
      expect(screen.getByText('Edit Config')).toBeInTheDocument();
    });

    fireEvent.click(screen.getByText('Edit Config'));
    expect(screen.getByText('Save')).toBeInTheDocument();

    fireEvent.click(screen.getByText('Cancel'));
    // Should be back to read-only mode with Edit Config button visible
    await waitFor(() => {
      expect(screen.getByText('Edit Config')).toBeInTheDocument();
    });
  });

  it('shows members tab with email and role badge', async () => {
    renderSettingsPage();
    await waitFor(() => {
      expect(screen.getByText('Members (1)')).toBeInTheDocument();
    });

    fireEvent.click(screen.getByText('Members (1)'));

    await waitFor(() => {
      expect(screen.getByText('dev@test.com')).toBeInTheDocument();
      // "developer" appears in RoleBadge AND in the role dropdown; getAllByText returns at least 1
      const developerElements = screen.getAllByText('developer');
      expect(developerElements.length).toBeGreaterThanOrEqual(1);
      // Verify the RoleBadge span exists (it has the bg-blue-900/50 class)
      const badge = developerElements.find(
        (el) => el.className.includes('bg-blue-900/50')
      );
      expect(badge).toBeTruthy();
    });
  });

  it('shows feature toggles tab with self-approve checkbox', async () => {
    renderSettingsPage();
    await waitFor(() => {
      expect(screen.getByText('Feature Toggles')).toBeInTheDocument();
    });

    fireEvent.click(screen.getByText('Feature Toggles'));

    await waitFor(() => {
      expect(screen.getByText('Allow self-approve')).toBeInTheDocument();
      expect(screen.getByText('Authors can merge their own merge requests')).toBeInTheDocument();
    });
  });

  it('displays the invite member form in members tab', async () => {
    renderSettingsPage();
    await waitFor(() => {
      expect(screen.getByText('Members (1)')).toBeInTheDocument();
    });

    fireEvent.click(screen.getByText('Members (1)'));

    await waitFor(() => {
      expect(screen.getByText('Invite Member')).toBeInTheDocument();
      expect(screen.getByPlaceholderText('user@example.com')).toBeInTheDocument();
      expect(screen.getByText('Invite')).toBeInTheDocument();
    });
  });

  it('displays the add environment form in environments tab', async () => {
    renderSettingsPage();
    await waitFor(() => {
      expect(screen.getByText('Environments')).toBeInTheDocument();
    });

    fireEvent.click(screen.getByText('Environments'));

    await waitFor(() => {
      expect(screen.getByText('Add Environment')).toBeInTheDocument();
      expect(screen.getByPlaceholderText('production')).toBeInTheDocument();
      expect(screen.getByPlaceholderText('main')).toBeInTheDocument();
      expect(screen.getByText('Add')).toBeInTheDocument();
    });
  });
});

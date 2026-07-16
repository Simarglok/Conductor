import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import { render, screen, fireEvent, waitFor } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
import AdminPage from '../AdminPage';

// ── Mock data ──────────────────────────────────────────────────────────────

const mockUsers = [
  {
    id: '1',
    email: 'admin@test.com',
    display_name: 'Admin',
    is_admin: true,
    is_active: true,
    created_at: '2026-01-01',
  },
];

const mockRoles = [
  {
    id: 'r1',
    name: 'super_admin',
    description: 'Full access',
    is_system: true,
    created_at: '2026-01-01',
  },
  {
    id: 'r2',
    name: 'developer',
    description: 'Develop and test',
    is_system: true,
    created_at: '2026-01-01',
  },
];

const mockPerms = [{ id: 'p1', resource: 'dag', action: 'view', constraint: null }];

const mockProjects = [
  {
    id: '1',
    name: 'DW',
    slug: 'data-warehouse',
    member_count: 5,
    airflow_status: 'running',
    created_at: '2026-01-01',
  },
];

// ── Fetch mock ─────────────────────────────────────────────────────────────

function createFetchMock() {
  return vi.fn((url: string, options?: RequestInit) => {
    const urlStr = url.toString();

    // GET /admin/users
    if (urlStr.includes('/admin/users') && (!options || options.method === undefined || options.method === 'GET')) {
      return Promise.resolve({
        ok: true,
        status: 200,
        json: () => Promise.resolve(mockUsers),
      });
    }

    // PATCH /admin/users/{id}
    if (urlStr.includes('/admin/users/') && options?.method === 'PATCH') {
      return Promise.resolve({
        ok: true,
        status: 200,
        json: () => Promise.resolve({ ...mockUsers[0], is_admin: false }),
      });
    }

    // GET /admin/roles
    if (urlStr.includes('/admin/roles') && !urlStr.includes('/permissions') && (!options || options.method === undefined || options.method === 'GET')) {
      return Promise.resolve({
        ok: true,
        status: 200,
        json: () => Promise.resolve(mockRoles),
      });
    }

    // POST /admin/roles
    if (urlStr.includes('/admin/roles') && !urlStr.includes('/permissions') && options?.method === 'POST') {
      return Promise.resolve({
        ok: true,
        status: 201,
        json: () =>
          Promise.resolve({
            id: 'r3',
            name: 'viewer',
            description: 'Read-only',
            is_system: false,
            created_at: '2026-01-01',
          }),
      });
    }

    // GET /admin/roles/{id}/permissions
    if (urlStr.includes('/permissions') && (!options || options.method === undefined || options.method === 'GET')) {
      return Promise.resolve({
        ok: true,
        status: 200,
        json: () => Promise.resolve(mockPerms),
      });
    }

    // POST /admin/roles/{id}/permissions
    if (urlStr.includes('/permissions') && options?.method === 'POST') {
      return Promise.resolve({
        ok: true,
        status: 201,
        json: () => Promise.resolve({ id: 'p2', resource: 'dag', action: 'run', constraint: null }),
      });
    }

    // DELETE /admin/roles/{id}/permissions/{perm_id}
    if (urlStr.includes('/permissions/') && options?.method === 'DELETE') {
      return Promise.resolve({ ok: true, status: 204, json: () => Promise.resolve(null) });
    }

    // GET /admin/projects
    if (urlStr.includes('/admin/projects') && (!options || options.method === undefined || options.method === 'GET')) {
      return Promise.resolve({
        ok: true,
        status: 200,
        json: () => Promise.resolve(mockProjects),
      });
    }

    return Promise.resolve({ ok: true, status: 200, json: () => Promise.resolve(null) });
  });
}

function renderAdminPage() {
  return render(
    <MemoryRouter>
      <AdminPage />
    </MemoryRouter>
  );
}

// ── Tests ──────────────────────────────────────────────────────────────────

describe('AdminPage', () => {
  beforeEach(() => {
    window.fetch = createFetchMock() as any;
  });

  afterEach(() => {
    delete (window as any).fetch;
  });

  it('renders 4 sidebar sections', async () => {
    renderAdminPage();

    await waitFor(() => {
      expect(screen.getByText('Users')).toBeInTheDocument();
      expect(screen.getByText('All Projects')).toBeInTheDocument();
      expect(screen.getByText('Roles & Permissions')).toBeInTheDocument();
      expect(screen.getByText('System Settings')).toBeInTheDocument();
    });
  });

  it('switches section and shows correct content', async () => {
    renderAdminPage();

    // Default: users section
    await waitFor(() => {
      expect(screen.getByText('admin@test.com')).toBeInTheDocument();
    });

    // Switch to projects
    fireEvent.click(screen.getByText('All Projects'));
    await waitFor(() => {
      expect(screen.getByText('DW')).toBeInTheDocument();
    });

    // Switch to roles
    fireEvent.click(screen.getByText('Roles & Permissions'));
    await waitFor(() => {
      expect(screen.getByText('super_admin')).toBeInTheDocument();
    });

    // Switch to system
    fireEvent.click(screen.getByText('System Settings'));
    await waitFor(() => {
      expect(screen.getByText('System settings coming soon')).toBeInTheDocument();
    });
  });

  it('shows users table with data', async () => {
    renderAdminPage();

    await waitFor(() => {
      expect(screen.getByText('admin@test.com')).toBeInTheDocument();
      // "Admin" appears in sidebar heading AND as display_name; getAllByText returns both
      const adminElements = screen.getAllByText('Admin');
      expect(adminElements.length).toBeGreaterThanOrEqual(2);
      expect(screen.getByText('Active')).toBeInTheDocument();
    });
  });

  it('shows projects table with names and status badges', async () => {
    renderAdminPage();

    fireEvent.click(screen.getByText('All Projects'));

    await waitFor(() => {
      expect(screen.getByText('DW')).toBeInTheDocument();
      expect(screen.getByText('data-warehouse')).toBeInTheDocument();
      expect(screen.getByText('5')).toBeInTheDocument();
      expect(screen.getByText('running')).toBeInTheDocument();
    });
  });

  it('renders all roles in the roles list', async () => {
    renderAdminPage();

    fireEvent.click(screen.getByText('Roles & Permissions'));

    await waitFor(() => {
      expect(screen.getByText('super_admin')).toBeInTheDocument();
      expect(screen.getByText('Full access')).toBeInTheDocument();
      expect(screen.getByText('developer')).toBeInTheDocument();
      expect(screen.getByText('Develop and test')).toBeInTheDocument();
    });
  });

  it('opens role editor when a role is clicked', async () => {
    renderAdminPage();

    fireEvent.click(screen.getByText('Roles & Permissions'));

    await waitFor(() => {
      expect(screen.getByText('super_admin')).toBeInTheDocument();
    });

    fireEvent.click(screen.getByText('super_admin'));

    await waitFor(() => {
      expect(screen.getByText('Edit Role: super_admin')).toBeInTheDocument();
      expect(screen.getByText('Permissions')).toBeInTheDocument();
      expect(screen.getByText('View DAGs')).toBeInTheDocument();
    });
  });

  it('toggles permission checkboxes', async () => {
    renderAdminPage();

    fireEvent.click(screen.getByText('Roles & Permissions'));

    await waitFor(() => {
      expect(screen.getByText('super_admin')).toBeInTheDocument();
    });

    fireEvent.click(screen.getByText('super_admin'));

    await waitFor(() => {
      expect(screen.getByText('View DAGs')).toBeInTheDocument();
    });

    // Find the "View DAGs" checkbox (dag.view is in mockPerms, so it should be checked)
    const viewDagsLabel = screen.getByText('View DAGs');
    const viewDagsCheckbox = viewDagsLabel.parentElement?.querySelector('input[type="checkbox"]') as HTMLInputElement;
    expect(viewDagsCheckbox).toBeTruthy();
    expect(viewDagsCheckbox?.checked).toBe(true);

    // Find "Run DAGs" checkbox (not in mockPerms, should be unchecked)
    const runDagsLabel = screen.getByText('Run DAGs');
    const runDagsCheckbox = runDagsLabel.parentElement?.querySelector('input[type="checkbox"]') as HTMLInputElement;
    expect(runDagsCheckbox).toBeTruthy();
    expect(runDagsCheckbox?.checked).toBe(false);

    // Toggle "Run DAGs" on
    fireEvent.click(runDagsCheckbox!);

    // Should trigger POST /admin/roles/r1/permissions
    await waitFor(() => {
      expect(runDagsCheckbox?.checked).toBe(true);
    });
  });

  it('shows new role form when "Create Custom Role" button is clicked', async () => {
    renderAdminPage();

    fireEvent.click(screen.getByText('Roles & Permissions'));

    await waitFor(() => {
      expect(screen.getByText('+ Create Custom Role')).toBeInTheDocument();
    });

    fireEvent.click(screen.getByText('+ Create Custom Role'));

    await waitFor(() => {
      expect(screen.getByPlaceholderText('Role name')).toBeInTheDocument();
      expect(screen.getByPlaceholderText('Description')).toBeInTheDocument();
      expect(screen.getByText('Create')).toBeInTheDocument();
      expect(screen.getByText('Cancel')).toBeInTheDocument();
    });
  });

  it('shows system settings placeholder', async () => {
    renderAdminPage();

    fireEvent.click(screen.getByText('System Settings'));

    await waitFor(() => {
      expect(screen.getByText('System settings coming soon')).toBeInTheDocument();
    });
  });
});
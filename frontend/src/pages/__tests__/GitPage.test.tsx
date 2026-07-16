import { describe, it, expect, vi, beforeAll, afterAll, beforeEach } from 'vitest';
import { render, screen, waitFor, fireEvent } from '@testing-library/react';
import { MemoryRouter, Route, Routes } from 'react-router-dom';
import GitPage from '../../pages/GitPage';

// ── Mock data ──────────────────────────────────────────────────────────────

const mockMrs = [
  {
    id: '1',
    title: 'Add orders model',
    source_branch: 'feature/orders',
    target_branch: 'main',
    status: 'open',
    author_name: 'dev',
    author_id: 'u1',
    created_at: '2026-07-01T00:00:00Z',
  },
  {
    id: '2',
    title: 'Fix login bug',
    source_branch: 'fix/login',
    target_branch: 'main',
    status: 'merged',
    author_name: 'alice',
    author_id: 'u2',
    created_at: '2026-06-28T00:00:00Z',
  },
  {
    id: '3',
    title: 'Old feature',
    source_branch: 'old/feature',
    target_branch: 'main',
    status: 'closed',
    author_name: 'bob',
    author_id: 'u3',
    created_at: '2026-06-15T00:00:00Z',
  },
];

const mockBranches = [
  { name: 'main', last_commit_sha: 'abc1234', ahead_of_main: 0, behind_main: 0 },
  { name: 'feature/orders', last_commit_sha: 'def5678', ahead_of_main: 3, behind_main: 0 },
  { name: 'fix/login', last_commit_sha: 'ghi9012', ahead_of_main: 0, behind_main: 2 },
];

const mockCommits = [
  {
    sha: 'abc1234def',
    message: 'Add orders model',
    author_name: 'dev',
    author_email: 'dev@test.com',
    date: '2026-07-01T00:00:00Z',
  },
  {
    sha: 'xyz9876abc',
    message: 'Fix login redirect',
    author_name: 'alice',
    author_email: 'alice@test.com',
    date: '2026-06-28T00:00:00Z',
  },
];

const mockChecks = [
  { name: 'build', status: 'completed', conclusion: 'success', details_url: 'https://ci.example.com/1' },
  { name: 'lint', status: 'completed', conclusion: 'failure', details_url: 'https://ci.example.com/2' },
  { name: 'test', status: 'in_progress', conclusion: '', details_url: 'https://ci.example.com/3' },
];

const mockSettings = { self_approve_enabled: false };

// ── Mock fetch factory ─────────────────────────────────────────────────────

// Track calls made to fetch for test assertions
let fetchCalls: { url: string; method: string }[] = [];

function createMockFetch() {
  fetchCalls = [];
  return vi.fn((url: RequestInfo | URL, init?: RequestInit) => {
    const urlStr = String(url);
    fetchCalls.push({ url: urlStr, method: init?.method || 'GET' });

    // Settings
    if (urlStr.includes('/settings')) {
      return Promise.resolve({
        ok: true,
        status: 200,
        json: () => Promise.resolve(mockSettings),
      });
    }

    // Checks for MR 1
    if (urlStr.includes('/merge-requests/1/checks')) {
      return Promise.resolve({
        ok: true,
        status: 200,
        json: () => Promise.resolve(mockChecks),
      });
    }

    // Checks for MR 2
    if (urlStr.includes('/merge-requests/2/checks')) {
      return Promise.resolve({
        ok: true,
        status: 200,
        json: () => Promise.resolve([]),
      });
    }

    // Checks for MR 3
    if (urlStr.includes('/merge-requests/3/checks')) {
      return Promise.resolve({
        ok: true,
        status: 200,
        json: () => Promise.resolve([]),
      });
    }

    // Merge request list (exclude checks, merge, close endpoints)
    if (
      urlStr.includes('/git/merge-requests') &&
      !urlStr.includes('/checks') &&
      !urlStr.endsWith('/merge') &&
      !urlStr.endsWith('/close')
    ) {
      return Promise.resolve({
        ok: true,
        status: 200,
        json: () => Promise.resolve(mockMrs),
      });
    }

    // Branches
    if (urlStr.includes('/git/branches')) {
      return Promise.resolve({
        ok: true,
        status: 200,
        json: () => Promise.resolve(mockBranches),
      });
    }

    // Commits
    if (urlStr.includes('/git/commits')) {
      return Promise.resolve({
        ok: true,
        status: 200,
        json: () => Promise.resolve(mockCommits),
      });
    }

    // Default fallback (merge, close, etc — return success)
    return Promise.resolve({
      ok: true,
      status: 200,
      json: () => Promise.resolve({}),
    });
  });
}

function renderGitPage() {
  return render(
    <MemoryRouter initialEntries={['/projects/test-project/git']}>
      <Routes>
        <Route path="/projects/:slug/git" element={<GitPage />} />
      </Routes>
    </MemoryRouter>
  );
}

// ── Tests ──────────────────────────────────────────────────────────────────

describe('GitPage', () => {
  beforeAll(() => {
    vi.spyOn(Storage.prototype, 'getItem').mockReturnValue('test-token');
  });

  beforeEach(() => {
    window.fetch = createMockFetch() as any;
  });

  afterAll(() => {
    delete (window as any).fetch;
    vi.restoreAllMocks();
  });

  // ── Branch info bar ───────────────────────────────────────────────────

  it('renders branch bar with branch name', async () => {
    renderGitPage();

    await waitFor(() => {
      // The branch name "main" appears in the BranchInfoBar
      expect(screen.getByText('Active:')).toBeInTheDocument();
    });

    // The BranchInfoBar renders branch name via font-mono text
    const branchNames = screen.getAllByText('main');
    expect(branchNames.length).toBeGreaterThanOrEqual(1);
  });

  it('renders Push and Create MR buttons in branch bar', async () => {
    renderGitPage();

    await waitFor(() => {
      expect(screen.getByText('Push')).toBeInTheDocument();
      expect(screen.getByText('Create MR')).toBeInTheDocument();
    });
  });

  // ── Tabs ──────────────────────────────────────────────────────────────

  it('renders 3 tabs with counts', async () => {
    renderGitPage();

    await waitFor(() => {
      expect(screen.getByText('Merge Requests (3)')).toBeInTheDocument();
    });

    expect(screen.getByText('Branches (3)')).toBeInTheDocument();
    expect(screen.getByText('Commits')).toBeInTheDocument();
  });

  it('switches tab content when clicking branches tab', async () => {
    renderGitPage();

    await waitFor(() => {
      expect(screen.getByText('Merge Requests (3)')).toBeInTheDocument();
    });

    fireEvent.click(screen.getByText('Branches (3)'));

    await waitFor(() => {
      expect(screen.getByText('feature/orders')).toBeInTheDocument();
      expect(screen.getByText('fix/login')).toBeInTheDocument();
    });
  });

  it('switches tab content when clicking commits tab', async () => {
    renderGitPage();

    await waitFor(() => {
      expect(screen.getByText('Merge Requests (3)')).toBeInTheDocument();
    });

    fireEvent.click(screen.getByText('Commits'));

    await waitFor(() => {
      expect(screen.getByText('Add orders model')).toBeInTheDocument();
    });
  });

  // ── MR items ──────────────────────────────────────────────────────────

  it('shows MR items with title, status badge, branch arrows, author', async () => {
    renderGitPage();

    await waitFor(() => {
      expect(screen.getByText('Add orders model')).toBeInTheDocument();
    });

    // Status badges
    expect(screen.getByText('OPEN')).toBeInTheDocument();
    expect(screen.getByText('MERGED')).toBeInTheDocument();
    expect(screen.getByText('CLOSED')).toBeInTheDocument();

    // Branch names in MR cards
    expect(screen.getByText('feature/orders')).toBeInTheDocument();
    expect(screen.getByText('fix/login')).toBeInTheDocument();

    // Author
    expect(screen.getByText('dev')).toBeInTheDocument();
    expect(screen.getByText('alice')).toBeInTheDocument();
    expect(screen.getByText('bob')).toBeInTheDocument();
  });

  it('shows CheckBadge items for MRs with checks', async () => {
    renderGitPage();

    await waitFor(() => {
      expect(screen.getByText('✅ build')).toBeInTheDocument();
    });

    expect(screen.getByText('❌ lint')).toBeInTheDocument();
    expect(screen.getByText('⏳ test')).toBeInTheDocument();
  });

  it('shows Merge and Close buttons for open MRs', async () => {
    renderGitPage();

    await waitFor(() => {
      expect(screen.getByText('Add orders model')).toBeInTheDocument();
    });

    // The open MR (Add orders model) should have Merge and Close buttons
    expect(screen.getByText('Merge')).toBeInTheDocument();
    expect(screen.getByText('Close')).toBeInTheDocument();
  });

  it('only shows Merge/Close for open MRs (not merged or closed)', async () => {
    renderGitPage();

    await waitFor(() => {
      expect(screen.getByText('Fix login bug')).toBeInTheDocument();
    });

    // There should only be one Merge button and one Close button (for the open MR)
    const mergeButtons = screen.getAllByText('Merge');
    const closeButtons = screen.getAllByText('Close');
    expect(mergeButtons).toHaveLength(1);
    expect(closeButtons).toHaveLength(1);
  });

  // ── Merge action ──────────────────────────────────────────────────────

  it('calls merge API when Merge button is clicked', async () => {
    renderGitPage();

    await waitFor(() => {
      expect(screen.getByText('Merge')).toBeInTheDocument();
    });

    // Clear previous fetch calls (from initial data load)
    fetchCalls = [];

    fireEvent.click(screen.getByText('Merge'));

    await waitFor(() => {
      const mergeCall = fetchCalls.find((c) => c.url.includes('/merge-requests/1/merge'));
      expect(mergeCall).toBeTruthy();
      expect(mergeCall!.method).toBe('POST');
    });
  });

  it('calls close API when Close button is clicked', async () => {
    renderGitPage();

    await waitFor(() => {
      expect(screen.getByText('Close')).toBeInTheDocument();
    });

    fetchCalls = [];

    fireEvent.click(screen.getByText('Close'));

    await waitFor(() => {
      const closeCall = fetchCalls.find((c) => c.url.includes('/merge-requests/1/close'));
      expect(closeCall).toBeTruthy();
      expect(closeCall!.method).toBe('POST');
    });
  });

  // ── Create MR modal ───────────────────────────────────────────────────

  it('opens Create MR modal with form fields', async () => {
    renderGitPage();

    await waitFor(() => {
      expect(screen.getByText('Create MR')).toBeInTheDocument();
    });

    fireEvent.click(screen.getByText('Create MR'));

    await waitFor(() => {
      expect(screen.getByText('Create Merge Request')).toBeInTheDocument();
    });

    // Form fields
    expect(screen.getByText('Source Branch')).toBeInTheDocument();
    expect(screen.getByText('Target Branch')).toBeInTheDocument();
    expect(screen.getByText('Title')).toBeInTheDocument();
    expect(screen.getByText('Description (optional)')).toBeInTheDocument();

    // Buttons
    expect(screen.getByText('Cancel')).toBeInTheDocument();
    // There are two "Create MR" buttons: one in branch bar, one submit button
    const createButtons = screen.getAllByText('Create MR');
    expect(createButtons.length).toBeGreaterThanOrEqual(2);
  });

  it('closes modal when Cancel is clicked', async () => {
    renderGitPage();

    await waitFor(() => {
      expect(screen.getByText('Create MR')).toBeInTheDocument();
    });

    fireEvent.click(screen.getByText('Create MR'));

    await waitFor(() => {
      expect(screen.getByText('Create Merge Request')).toBeInTheDocument();
    });

    fireEvent.click(screen.getByText('Cancel'));

    await waitFor(() => {
      expect(screen.queryByText('Create Merge Request')).not.toBeInTheDocument();
    });
  });

  // ── Branches tab ──────────────────────────────────────────────────────

  it('shows branch names with ahead/behind indicators', async () => {
    renderGitPage();

    await waitFor(() => {
      expect(screen.getByText('Branches (3)')).toBeInTheDocument();
    });

    fireEvent.click(screen.getByText('Branches (3)'));

    await waitFor(() => {
      // Branch name appears in branch list (not just BranchInfoBar)
      expect(screen.getByText('feature/orders')).toBeInTheDocument();
      expect(screen.getByText('fix/login')).toBeInTheDocument();

      // Ahead indicator
      expect(screen.getByText('↑ 3')).toBeInTheDocument();
      // Behind indicator
      expect(screen.getByText('↓ 2')).toBeInTheDocument();
      // Up to date indicator
      expect(screen.getByText('up to date')).toBeInTheDocument();
    });
  });

  it('shows short SHA in branches tab', async () => {
    renderGitPage();

    await waitFor(() => {
      expect(screen.getByText('Branches (3)')).toBeInTheDocument();
    });

    fireEvent.click(screen.getByText('Branches (3)'));

    await waitFor(() => {
      expect(screen.getByText('abc1234')).toBeInTheDocument();
      expect(screen.getByText('def5678')).toBeInTheDocument();
    });
  });

  // ── Commits tab ───────────────────────────────────────────────────────

  it('shows commit SHA, message, author, and date', async () => {
    renderGitPage();

    await waitFor(() => {
      expect(screen.getByText('Commits')).toBeInTheDocument();
    });

    fireEvent.click(screen.getByText('Commits'));

    await waitFor(() => {
      // Short SHA
      expect(screen.getByText('abc1234')).toBeInTheDocument();
      // Message
      expect(screen.getByText('Add orders model')).toBeInTheDocument();
      // Author
      expect(screen.getByText('dev')).toBeInTheDocument();
      // Second commit
      expect(screen.getByText('xyz9876')).toBeInTheDocument();
      expect(screen.getByText('Fix login redirect')).toBeInTheDocument();
      expect(screen.getByText('alice')).toBeInTheDocument();
    });
  });
});

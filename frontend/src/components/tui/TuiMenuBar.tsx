/**
 * Top menu bar of the TUI layout with pull-down menus (F9 opens the first).
 * While a menu is open: ←/→ switch menus, ↑/↓ move, Enter runs the item,
 * Esc / F9 / F10 close it. The right side shows the user and invite quota.
 */

import { useEffect, useMemo, useState } from 'react';
import { useNavigate, useParams } from 'react-router';
import { useQuery } from '@tanstack/react-query';
import { useAuth } from '../../contexts/AuthContext';
import { fetchInvitesConfig } from '../../api/invites';
import { useTheme } from '../../theme/ThemeContext';
import { THEME_LABELS, THEME_PREFERENCES } from '../../theme/theme';
import ImportDialog from '../ImportDialog';
import TuiBorder from './TuiBorder';
import { useTui } from './TuiContext';

interface MenuItem {
  id: string;
  label: string;
  /** Shortcut shown on the right, e.g. "F7". */
  hint?: string;
  disabled?: boolean;
  /** Set for radio items (themes). */
  checked?: boolean;
  onSelect: () => void;
}

interface Menu {
  title: string;
  items: MenuItem[];
}

/** Characters taken by each title in the bar (one space on each side). */
const TITLE_PADDING = 2;

function firstEnabled(items: MenuItem[], from: number, step: 1 | -1): number {
  for (let i = 0; i < items.length; i++) {
    const index = (from + step * i + items.length * 2) % items.length;
    if (!items[index].disabled) return index;
  }
  return -1;
}

export default function TuiMenuBar() {
  const { user, logout } = useAuth();
  const { notebookId, noteId } = useParams();
  const navigate = useNavigate();
  const { preference, setPreference } = useTheme();
  const tui = useTui();
  const { menuOpen, setMenuOpen, pane, focus } = tui;
  const [menuIndex, setMenuIndex] = useState(0);
  const [itemIndex, setItemIndex] = useState(0);
  const [importing, setImporting] = useState(false);

  const { data: invitesConfig } = useQuery({
    queryKey: ['invites', 'config'],
    queryFn: fetchInvitesConfig,
  });

  const menus = useMemo<Menu[]>(() => {
    const notebooksShown = tui.visiblePanes.includes('notebooks');
    const options: MenuItem[] = THEME_PREFERENCES.map((p) => ({
      id: `theme-${p}`,
      label: THEME_LABELS[p],
      checked: preference === p,
      onSelect: () => setPreference(p),
    }));
    if (invitesConfig?.invites_enabled) {
      options.push({ id: 'invites', label: 'Invites…', onSelect: () => navigate('/invites') });
    }
    options.push({ id: 'settings', label: 'Settings…', onSelect: () => navigate('/settings') });

    return [
      {
        title: 'File',
        items: [
          {
            id: 'new-notebook',
            label: 'New notebook…',
            hint: 'F7',
            disabled: !notebooksShown,
            onSelect: () => tui.runList('notebooks', 'new'),
          },
          {
            id: 'new-note',
            label: 'New note…',
            hint: 'F7',
            disabled: !notebookId,
            onSelect: () => tui.runList('notes', 'new'),
          },
          { id: 'import', label: 'Import from Evernote…', onSelect: () => setImporting(true) },
          { id: 'logout', label: 'Log out', onSelect: () => void logout() },
        ],
      },
      {
        title: 'Note',
        items: [
          { id: 'edit', label: 'Edit', hint: 'F4', disabled: !noteId, onSelect: () => focus('editor') },
          { id: 'tags', label: 'Tags', hint: 'F5', disabled: !noteId, onSelect: () => focus('tags') },
          {
            id: 'share',
            label: 'Share…',
            hint: 'F2',
            disabled: !noteId,
            onSelect: () => tui.runList('notes', 'shareOpen'),
          },
          {
            id: 'delete',
            label: 'Delete…',
            hint: 'F8',
            disabled: !noteId,
            onSelect: () => tui.runList('notes', 'deleteOpen'),
          },
        ],
      },
      {
        title: 'View',
        items: [
          {
            id: 'toggle-notebooks',
            label: tui.notebooksHidden ? 'Show notebooks' : 'Hide notebooks',
            hint: 'F3',
            disabled: !notebookId,
            onSelect: () => tui.runFkey(3),
          },
          {
            id: 'filter',
            label: 'Filter list…',
            hint: 'F6',
            disabled: pane === 'editor',
            onSelect: () => tui.runFkey(6),
          },
          { id: 'classic', label: 'Classic layout', hint: 'F10', onSelect: () => tui.runFkey(10) },
        ],
      },
      { title: 'Options', items: options },
      {
        title: 'Help',
        items: [{ id: 'keys', label: 'Keys', hint: 'F1', onSelect: () => tui.setHelpOpen(true) }],
      },
    ];
  }, [tui, pane, focus, notebookId, noteId, preference, setPreference, invitesConfig, navigate, logout]);

  const openMenu = (index: number) => {
    setMenuIndex(index);
    setMenuOpen(true);
  };

  const close = () => {
    setMenuOpen(false);
    focus(pane);
  };

  const select = (item: MenuItem) => {
    if (item.disabled) return;
    setMenuOpen(false);
    item.onSelect();
  };

  // Opening (F9 or a click) highlights the menu's first enabled item.
  useEffect(() => {
    if (menuOpen) setItemIndex(firstEnabled(menus[menuIndex].items, 0, 1));
    // Only when a menu opens, not when its items are rebuilt.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [menuOpen, menuIndex]);

  useEffect(() => {
    if (!menuOpen) return;
    const items = menus[menuIndex].items;
    const onKeyDown = (e: KeyboardEvent) => {
      const switchTo = (index: number) => setMenuIndex(index);
      switch (e.key) {
        case 'ArrowLeft':
          switchTo((menuIndex - 1 + menus.length) % menus.length);
          break;
        case 'ArrowRight':
          switchTo((menuIndex + 1) % menus.length);
          break;
        case 'ArrowDown':
          setItemIndex(firstEnabled(items, itemIndex + 1, 1));
          break;
        case 'ArrowUp':
          setItemIndex(firstEnabled(items, itemIndex - 1, -1));
          break;
        case 'Enter':
        case ' ':
          if (items[itemIndex]) select(items[itemIndex]);
          break;
        case 'Escape':
        case 'F9':
        case 'F10':
          close();
          break;
        default:
          return;
      }
      e.preventDefault();
    };
    document.addEventListener('keydown', onKeyDown);
    return () => document.removeEventListener('keydown', onKeyDown);
  });

  const offsets = menus.map((_, i) =>
    menus.slice(0, i).reduce((sum, m) => sum + m.title.length + TITLE_PADDING, 1),
  );
  const current = menus[menuIndex];

  return (
    <header className="tui-menubar">
      <span className="tui-menubar-brand">≡</span>
      {menus.map((menu, i) => (
        <button
          key={menu.title}
          type="button"
          className={`tui-menubar-title${menuOpen && i === menuIndex ? ' open' : ''}`}
          aria-haspopup="menu"
          aria-expanded={menuOpen && i === menuIndex}
          onMouseDown={(e) => e.preventDefault()}
          onClick={() => (menuOpen && i === menuIndex ? close() : openMenu(i))}
        >
          {menu.title}
        </button>
      ))}
      <span className="tui-menubar-spacer" />
      <span className="tui-menubar-user">
        {user.firstname} {user.lastname} │ {user.invite_quota_remaining} invites
      </span>
      {menuOpen && (
        <>
          <div className="tui-menu-backdrop" onClick={close} />
          <div
            className="tui-menu tui-framed"
            role="menu"
            aria-label={current.title}
            style={{ left: `${offsets[menuIndex]}ch` }}
          >
            <TuiBorder active />
            {current.items.map((item, i) => (
              <button
                key={item.id}
                type="button"
                role={item.checked === undefined ? 'menuitem' : 'menuitemradio'}
                aria-checked={item.checked}
                aria-disabled={item.disabled || undefined}
                className={`tui-menu-item${i === itemIndex ? ' cursor' : ''}`}
                onMouseDown={(e) => e.preventDefault()}
                onMouseEnter={() => !item.disabled && setItemIndex(i)}
                onClick={() => select(item)}
              >
                <span>
                  {item.checked !== undefined && (item.checked ? '(•) ' : '( ) ')}
                  {item.label}
                </span>
                {item.hint && <span className="tui-menu-hint">{item.hint}</span>}
              </button>
            ))}
          </div>
        </>
      )}
      {importing && <ImportDialog onClose={() => setImporting(false)} />}
    </header>
  );
}

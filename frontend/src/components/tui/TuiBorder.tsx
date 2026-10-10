/**
 * Text-drawn frame around a TUI pane or dialog. It is an overlay: the
 * parent must be `position: relative` and leave one line / one character of
 * padding on each side (`.tui-framed`). Edges are long runs of box-drawing
 * characters clipped by `overflow: hidden`, so the frame follows any size.
 * The active pane is drawn with double lines.
 */

const SINGLE = { tl: '┌', tr: '┐', bl: '└', br: '┘', h: '─', v: '│' };
const DOUBLE = { tl: '╔', tr: '╗', bl: '╚', br: '╝', h: '═', v: '║' };

/** Longer than any realistic pane, in characters / lines. */
const EDGE_CHARS = 600;
const EDGE_LINES = 300;

export default function TuiBorder({
  title,
  footer,
  active = false,
}: {
  title?: string;
  footer?: string;
  active?: boolean;
}) {
  const c = active ? DOUBLE : SINGLE;
  const horizontal = c.h.repeat(EDGE_CHARS);
  const vertical = `${c.v}\n`.repeat(EDGE_LINES);
  return (
    <div className={`tui-border${active ? ' active' : ''}`} aria-hidden="true">
      <div className="tui-border-row top">
        <span>{c.tl}{c.h}</span>
        {title && <span className="tui-border-label">[ {title} ]</span>}
        <span className="tui-border-fill">{horizontal}</span>
        <span>{c.tr}</span>
      </div>
      <div className="tui-border-side left">{vertical}</div>
      <div className="tui-border-side right">{vertical}</div>
      <div className="tui-border-row bottom">
        <span>{c.bl}{c.h}</span>
        {footer && <span className="tui-border-label">[ {footer} ]</span>}
        <span className="tui-border-fill">{horizontal}</span>
        <span>{c.br}</span>
      </div>
    </div>
  );
}

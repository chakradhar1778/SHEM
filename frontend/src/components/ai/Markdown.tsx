import { Fragment, type ReactNode } from 'react';

/**
 * Minimal, safe Markdown → React renderer for AI replies.
 * Supports headings, paragraphs, bullet/numbered lists, fenced code, quotes,
 * rules, **bold**, *italic*, `code` and [links](https://…). Never uses innerHTML.
 */

const SAFE_URL = /^(https?:\/\/|mailto:|\/(?!\/))/i;

function renderInline(text: string, keyBase: string): ReactNode[] {
  const out: ReactNode[] = [];
  // order matters: code first so its contents are not formatted
  const re = /(`[^`\n]+`)|(\*\*[^*\n]+?\*\*|__[^_\n]+?__)|(\*[^*\s][^*\n]*?\*|_[^_\s][^_\n]*?_)|(\[[^\]\n]+\]\([^)\s]+\))/g;
  let last = 0;
  let m: RegExpExecArray | null;
  let i = 0;
  while ((m = re.exec(text)) !== null) {
    if (m.index > last) out.push(text.slice(last, m.index));
    const tok = m[0];
    const k = `${keyBase}-${i++}`;
    if (m[1]) out.push(<code key={k} className="md-code">{tok.slice(1, -1)}</code>);
    else if (m[2]) out.push(<strong key={k}>{renderInline(tok.slice(2, -2), k)}</strong>);
    else if (m[3]) out.push(<em key={k}>{renderInline(tok.slice(1, -1), k)}</em>);
    else if (m[4]) {
      const close = tok.indexOf('](');
      const label = tok.slice(1, close);
      const href = tok.slice(close + 2, -1);
      out.push(
        SAFE_URL.test(href) ? (
          <a key={k} href={href} target={href.startsWith('/') ? undefined : '_blank'} rel="noopener noreferrer">{label}</a>
        ) : (
          label
        )
      );
    }
    last = m.index + tok.length;
  }
  if (last < text.length) out.push(text.slice(last));
  return out;
}

function withBreaks(lines: string[], keyBase: string): ReactNode[] {
  return lines.flatMap((line, i) => {
    const nodes = renderInline(line, `${keyBase}-l${i}`);
    return i < lines.length - 1 ? [...nodes, <br key={`${keyBase}-br${i}`} />] : nodes;
  });
}

type Block =
  | { kind: 'h'; level: number; text: string }
  | { kind: 'p'; lines: string[] }
  | { kind: 'ul' | 'ol'; items: string[]; start: number }
  | { kind: 'code'; text: string }
  | { kind: 'quote'; lines: string[] }
  | { kind: 'hr' };

function parseBlocks(src: string): Block[] {
  const lines = src.replace(/\r\n?/g, '\n').split('\n');
  const blocks: Block[] = [];
  let i = 0;
  while (i < lines.length) {
    const line = lines[i];
    if (!line.trim()) {
      i += 1;
      continue;
    }
    if (line.trimStart().startsWith('```')) {
      const body: string[] = [];
      i += 1;
      while (i < lines.length && !lines[i].trimStart().startsWith('```')) body.push(lines[i++]);
      i += 1;
      blocks.push({ kind: 'code', text: body.join('\n') });
      continue;
    }
    const h = /^(#{1,6})\s+(.*)$/.exec(line);
    if (h) {
      blocks.push({ kind: 'h', level: h[1].length, text: h[2].replace(/#+\s*$/, '') });
      i += 1;
      continue;
    }
    if (/^\s*([-*_])\s*(\1\s*){2,}$/.test(line)) {
      blocks.push({ kind: 'hr' });
      i += 1;
      continue;
    }
    if (/^\s*>/.test(line)) {
      const q: string[] = [];
      while (i < lines.length && /^\s*>/.test(lines[i])) q.push(lines[i++].replace(/^\s*>\s?/, ''));
      blocks.push({ kind: 'quote', lines: q });
      continue;
    }
    const ul = /^\s*[-*+]\s+/;
    const ol = /^\s*(\d+)[.)]\s+/;
    if (ul.test(line) || ol.test(line)) {
      const ordered = !ul.test(line);
      const start = ordered ? Number(ol.exec(line)?.[1] ?? 1) : 1;
      const items: string[] = [];
      const marker = ordered ? ol : ul;
      while (i < lines.length && lines[i].trim()) {
        if (marker.test(lines[i])) items.push(lines[i].replace(marker, ''));
        else if (items.length && /^\s{2,}\S/.test(lines[i])) items[items.length - 1] += ` ${lines[i].trim()}`;
        else break;
        i += 1;
      }
      blocks.push({ kind: ordered ? 'ol' : 'ul', items, start });
      continue;
    }
    const para: string[] = [];
    while (
      i < lines.length &&
      lines[i].trim() &&
      !/^(#{1,6})\s+/.test(lines[i]) &&
      !lines[i].trimStart().startsWith('```') &&
      !ul.test(lines[i]) &&
      !ol.test(lines[i]) &&
      !/^\s*>/.test(lines[i])
    ) {
      para.push(lines[i++]);
    }
    blocks.push({ kind: 'p', lines: para });
  }
  return blocks;
}

export function Markdown({ text, className }: { text: string; className?: string }) {
  const blocks = parseBlocks(text);
  return (
    <div className={`md ${className ?? ''}`}>
      {blocks.map((b, i) => {
        const k = `b${i}`;
        switch (b.kind) {
          case 'h': {
            const level = Math.min(6, b.level + 2) as 3 | 4 | 5 | 6; // keep chat headings small
            const Tag = `h${level}` as const;
            return <Tag key={k} className="md-h">{renderInline(b.text, k)}</Tag>;
          }
          case 'p':
            return <p key={k}>{withBreaks(b.lines, k)}</p>;
          case 'ul':
            return <ul key={k}>{b.items.map((it, j) => <li key={j}>{renderInline(it, `${k}-${j}`)}</li>)}</ul>;
          case 'ol':
            return <ol key={k} start={b.start}>{b.items.map((it, j) => <li key={j}>{renderInline(it, `${k}-${j}`)}</li>)}</ol>;
          case 'code':
            return <pre key={k} className="md-pre"><code>{b.text}</code></pre>;
          case 'quote':
            return <blockquote key={k}>{withBreaks(b.lines, k)}</blockquote>;
          case 'hr':
            return <hr key={k} />;
          default:
            return <Fragment key={k} />;
        }
      })}
    </div>
  );
}

import { describe, expect, it } from 'vitest';
import { eventLinks } from './eventLinks';

describe('eventLinks', () => {
  it('gives nothing for a description without addresses', () => {
    expect(eventLinks('Come to the hall at 6pm.')).toEqual([]);
    expect(eventLinks('')).toEqual([]);
    expect(eventLinks(null)).toEqual([]);
  });

  it('lists each address once with its host, in the order typed', () => {
    const r = eventLinks('Form: https://forms.gle/abc. Rules: https://www.example.org/rules/ and again https://forms.gle/abc');
    expect(r).toEqual([
      { url: 'https://forms.gle/abc', host: 'forms.gle', rest: '/abc' },
      { url: 'https://www.example.org/rules/', host: 'example.org', rest: '/rules/' },
    ]);
  });

  it('takes bare social and Telegram addresses as https', () => {
    expect(eventLinks('see t.me/kbtu_club and instagram.com/club').map((x) => x.url))
      .toEqual(['https://t.me/kbtu_club', 'https://instagram.com/club']);
  });

  it('leaves out what the page already shows in its own row', () => {
    const r = eventLinks('Zoom: https://zoom.us/j/1 sign up https://Partner.kz/reg/ chat https://t.me/+abc',
      ['https://zoom.us/j/1', 'https://partner.kz/reg', null, 'https://t.me/+abc']);
    expect(r).toEqual([]);
  });

  it('shows the host alone for a bare site, the path and query apart from it', () => {
    const [site, doc] = eventLinks('https://kbtu.kz https://docs.google.com/document/d/abc/edit?usp=sharing');
    expect(site).toEqual({ url: 'https://kbtu.kz', host: 'kbtu.kz', rest: '' });
    expect(doc).toEqual({ url: 'https://docs.google.com/document/d/abc/edit?usp=sharing', host: 'docs.google.com', rest: '/document/d/abc/edit?usp=sharing' });
  });

  it('never shows a host a user:pass prefix would hide', () => {
    expect(eventLinks('https://kbtu.kz@evil.example/x')).toEqual([]);
  });

  it('keeps the group short', () => {
    const text = Array.from({ length: 9 }, (_, i) => `https://site${i}.kz`).join(' ');
    expect(eventLinks(text)).toHaveLength(6);
  });
});

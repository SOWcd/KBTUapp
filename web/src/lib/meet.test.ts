import { describe, expect, it } from 'vitest';
import { linkFill, meetHost, ONLINE_LINK } from './meet';

describe('meeting link', () => {
  it('shows the host only for a link that may open outside Telegram', () => {
    expect(meetHost('https://meet.google.com/abc-defg-hij')).toBe('meet.google.com');
    for (const bad of ['https://t.me/x_bot?start=room', 'https://a.telegram.me/x', 'https://telegram.dog/x', 'http://zoom.us/j/1',
      'javascript:alert(1)', 'https://u:p@zoom.us/j/1', 'https://zoom.us:8443/j/1', '', null, 'nope'])
      expect(meetHost(bad)).toBe('');
  });
  it('the editor refuses Telegram links and non-https', () => {
    expect(ONLINE_LINK.test('https://example.org/room')).toBe(true);
    for (const bad of ['https://t.me/x', 'https://telegram.me/x', 'http://zoom.us/j/1', 'https://zoom.us j'])
      expect(ONLINE_LINK.test(bad)).toBe(false);
  });
  it('"Add more" never replaces a link or a place silently', () => {
    const empty = { online: false, onlineUrl: '', place: '', tba: false };
    expect(linkFill('https://zoom.us/j/2', false, { ...empty, online: true, onlineUrl: 'https://zoom.us/j/1' })).toBe('fill'); // a first fill
    expect(linkFill('https://zoom.us/j/2', true, empty)).toBe('fill');
    expect(linkFill('https://zoom.us/j/2', true, { ...empty, online: true, onlineUrl: 'https://zoom.us/j/1' })).toBe('ask');
    expect(linkFill('https://zoom.us/j/1', true, { ...empty, online: true, onlineUrl: 'https://zoom.us/j/1' })).toBe('keep');
    expect(linkFill('https://zoom.us/j/2', true, { ...empty, place: '305' })).toBe('ask');
    expect(linkFill(undefined, true, empty)).toBe('keep');
  });
});

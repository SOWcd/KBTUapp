// Spy's places, in the server's order (server/kbtu/logic/spy.py LOCATIONS; a server test holds the two equal):
// campus first, then the city's and the classic ones. Names: spy.loc.<id> in lib/i18n.
export const SPY_LOCATIONS = [
  'library', 'canteen', 'lecture_hall', 'dorm', 'gym', 'dean_office', 'lab', 'coworking', 'exam', 'graduation',
  'hackathon', 'assembly_hall', 'club_fair', 'career_fair', 'metro', 'bus', 'coffee_shop', 'hospital', 'airport',
  'train', 'cinema', 'museum', 'bank', 'restaurant', 'theater', 'space_station', 'submarine', 'zoo',
  'supermarket', 'shymbulak', 'green_bazaar', 'wedding', 'concert', 'beach', 'police_station', 'pirate_ship',
] as const;
export type SpyLocation = (typeof SPY_LOCATIONS)[number];
/** the room's link: its QR and "share to chat" open the app straight into the room */
export const roomLink = (code: string): string => `https://t.me/KBTUappBot?startapp=g_${code}`;
/** a place's picture on its tile: the phone's own emoji, one per place
 *  ponytail: system emoji, so they look a little different on iOS and Android; the app's 3D set has no picture for
 *  about a dozen of these places. Once it does: `emoji/<name>.webp` names here and ui/Emoji in Spy.svelte's tile. */
export const SPY_ART: Record<SpyLocation, string> = {
  library: '📚', canteen: '🍲', lecture_hall: '🧑‍🏫', dorm: '🛏️', gym: '🏀', dean_office: '🗂️', lab: '🔬', coworking: '💻', exam: '📝', graduation: '🎓',
  hackathon: '💡', assembly_hall: '🎤', club_fair: '🧩', career_fair: '💼', metro: '🚇', bus: '🚌', coffee_shop: '☕', hospital: '🩺', airport: '✈️',
  train: '🚆', cinema: '🍿', museum: '🏛️', bank: '🏦', restaurant: '🍽️', theater: '🎭', space_station: '🚀', submarine: '🤿', zoo: '🦁',
  supermarket: '🛒', shymbulak: '⛷️', green_bazaar: '🍉', wedding: '💍', concert: '🎸', beach: '🏖️', police_station: '🚓', pirate_ship: '🏴‍☠️',
};

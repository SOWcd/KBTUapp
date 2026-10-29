// The student forum's topics: their 3D mark and order (server logic/threads.py TOPICS). Labels and hints are i18n keys
// bd.topic.<topic> and bd.hint.<topic>.
import type { Topic } from './api';

export const TOPICS: Topic[] = ['thing', 'go', 'help', 'vol', 'talk'];
export const TOPIC_EMOJI: Record<Topic, string> = {
  thing: 'briefcase_3d', go: 'pizza_3d', help: 'thinking_face_3d', vol: 'raising_hands_3d_default', talk: 'speech_balloon_3d',
};
/** "I'm in" counts people on these */
export const gathers = (t: Topic): boolean => t === 'go' || t === 'vol';

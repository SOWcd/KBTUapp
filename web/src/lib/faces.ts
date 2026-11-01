// The five faces of the rating after an event (SPEC §4.9), from 1 (confounded) to 5 (heart eyes): Fluent 3D, like the
// rest of the app's emoji (owner's yes).
export const FACES = ['confounded_face_3d', 'confused_face_3d', 'neutral_face_3d', 'slightly_smiling_face_3d', 'smiling_face_with_heart_eyes_3d'];

// People's faces in a cluster (Profile's Friends, Studio's Team): the ones with a photo first, then a fresh order each
// time the app opens, the same while it's open (the faces don't jump on every visit)
const SEED = Math.random() * 1e4;
const luck = (id: number) => { const x = Math.sin(id * 12.9898 + SEED) * 43758.5453; return x - Math.floor(x); };
export const photosFirst = <T extends { person: { id: number; avatar?: string | null } }>(l: T[]): T[] =>
  [...l].sort((a, b) => +!a.person.avatar - +!b.person.avatar || luck(a.person.id) - luck(b.person.id));

// The look of our map (KBTU App's), every floor and both themes: the one place a restyle edits. A floor file
// (floor-N.svg) is geometry only and names these as $tokens; build.mjs writes the light and dark SVGs the app loads.
// A pair is [light, dark]; a single value serves both.
export const STYLE = {
  // the walls' 2.5D, seen from straight above: the top face raised `H` units, `layers` flat copies of the side face
  // under it (H / layers no more than 1, the thinnest wall, or the face shows gaps), the dark's lit top
  H: 6, layers: 8, oSide: 1, side: ['#8C96B0', '#171B2A'], warmSide: ['#C4AE8A', '#18130D'],
  lit: [null, '#8C9AD0'], oLit: 0.35, litRise: 0.6,
  cast: [[1.2, 1.2], [2.4, 2.2]], oCast: [0.07, 0.25], // the contact shadow: flat copies of the walls on the floor, each [dx, dy]; no blur
  // outdoors, then indoors: corridors and halls, rooms
  asphalt: ['#DCE0EA', '#0A0B10'], ground: ['#F3F5FB', '#0A0B10'], floor: ['#FFFFFF', '#1C2132'], room: ['#EEF1F8', '#272E42'],
  warm: ['#FBF3E6', '#2E261B'], warmWall: ['#E2CFAE', '#6E5C44'], // floor 0 level: the canteen, Halyk, the north hall
  wall: ['#B9C1D3', '#4A5474'], outer: ['#A3ACC2', '#5D6990'], tread: ['#C3CADB', '#323A55'], step: ['#F7F8FC', '#222839'],
  void: ['#E6E9F1', '#12151F'], tileLine: ['#D3D8E4', '#1B2030'], slabLine: ['#D8D3C9', '#232633'],
  shadow: '#0B1020', oShade: [0.22, 0.6], black: '#000', oDrop: [0.16, 0.55],
  // words: none smaller than minText
  minText: 7, label: ['#5B6278', '#8C93AB'], num: ['#69718A', '#8189A3'], street: ['#9AA1B5', '#4E5670'], oMark: [0.4, 0.45],
  // openings and fixtures
  glass: ['#E4ECFF', '#24314F'], oGlassLine: [0.45, 0.7], door: ['#B88A5A', '#9C7448'],
  oak: ['#C08A50', '#8A5E35'], oakGrain: ['#8A5A2E', '#5E3D20'], pane: ['#BFE0F5', '#4F6E8F'],
  fixture: ['#FFFFFF', '#2A3248'], counter: ['#F3F5FA', '#222A3D'], cabin: ['#FFFFFF', '#171C2B'], white: '#fff',
  booth: '#E41E2B', oBooth: [0.22, 0.35], noEntry: '#FF4D4F',
  // the yards
  lawn: ['#CFE5C9', '#10231A'], tree: ['#A9CF9F', '#1A3A26'], leafEdge: ['#93BF88', '#143020'], oShine: [0.28, 0.06],
  bench: ['#C9B08C', '#5A4A36'],
  // kinds of place: the same in both themes; a room is washed in its kind's colour
  accent: '#3B6BFF', food: '#F5A53D', work: '#1FA35C', library: '#C9A27A', service: '#8EA0BF', lab: '#2EC4B0',
  stairs: '#AEB6CC', wcM: '#4FA8FF', wcF: '#FF6FAE', wcD: '#E5A800', water: '#45D0F0',
  oWash: [0.12, 0.16], oWashNamed: [0.18, 0.12], oCowork: [0.1, 0.14],
  rimBlue: '#9DB8FF', rimPink: '#FF9CC8',
};

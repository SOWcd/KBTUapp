// The look of our map (KBTU App's), every floor and both themes: the one place a restyle edits. A floor file
// (floor-N.svg) is geometry only and names these as $tokens; build.mjs writes the light and dark SVGs the app loads.
// A pair is [light, dark]; a single value serves both.
export const STYLE = {
  // the walls' 2.5D: the top face raised `H` units, `layers` copies of the side face under it, the dark's lit top
  H: 4, layers: 8, oSide: [0.5, 0.8], side: ['#9AA3BA', '#0B0E18'], lit: [null, '#8C9AD0'], oLit: 0.35, litRise: 0.6,
  // the ground and the building
  asphalt: ['#E2E5EE', '#0D0F17'], ground: ['#F3F5FB', '#07080F'], floor: ['#FFFFFF', '#10131C'], room: ['#EEF1F8', '#171B27'],
  warm: ['#FBF3E6', '#171512'], warmWall: ['#E2CFAE', '#423A30'], // floor 0 level: the canteen, Halyk
  wall: ['#B9C1D3', '#39415C'], outer: ['#A3ACC2', '#4C5778'], tread: ['#C3CADB', '#323A55'], step: ['#F7F8FC', '#141824'],
  void: ['#E6E9F1', '#0B0D14'], tileLine: ['#D3D8E4', '#1B2030'], slabLine: ['#D8D3C9', '#232633'],
  shadow: '#0B1020', oShade: [0.22, 0.6], black: '#000', oDrop: [0.16, 0.55],
  // words
  label: ['#5B6278', '#8C93AB'], num: ['#69718A', '#8189A3'], street: ['#9AA1B5', '#4E5670'], oMark: [0.26, 0.3],
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

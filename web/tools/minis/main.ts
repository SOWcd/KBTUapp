// The picker's minis drawn as the picker draws them (tools/scene-rasters.mjs takes their pictures)
import '@fontsource-variable/inter/opsz.css';
import '../../src/ui/tokens.css';
import '../../src/ui/base.css';
import { mount } from 'svelte';
import Minis from './Minis.svelte';

mount(Minis, { target: document.getElementById('app')! });

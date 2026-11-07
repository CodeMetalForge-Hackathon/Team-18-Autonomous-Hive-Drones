# Third-party components

The repository's Apache-2.0 license applies to the simulator code contributed here. These bundled components retain their upstream licenses.

## Three.js 0.170.0 — MIT

Source: https://github.com/mrdoob/three.js/tree/r170

Files: `vendor/three.module.mjs`, `vendor/OrbitControls.mjs`, `vendor/STLLoader.mjs`.

Copyright 2010–2024 Three.js authors. Full license: [vendor/THREE-LICENSE.txt](vendor/THREE-LICENSE.txt).

The helper files use local import paths so the viewer works without a CDN.

## M5Stack structural CAD — MIT

Source: https://github.com/m5stack/M5_Hardware/tree/ec351c516644b44defc145728cc029ced77381ff

Files: eight `assets/*.stl` models. Copyright (c) 2021 M5Stack. Full upstream license: [assets/M5STACK-LICENSE.txt](assets/M5STACK-LICENSE.txt).

Exact source URLs, the pinned commit and SHA-256 hashes are recorded in [assets/sources.json](assets/sources.json). Original STL files are bundled unchanged. The viewer selects part of the StickC casing mesh in memory and assembles the separate parts approximately; wheels and other missing pieces are procedural shapes.

These assets identify the hardware being simulated; this project is not an official M5Stack simulator.

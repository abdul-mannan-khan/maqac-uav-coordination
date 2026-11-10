# City height maps (OpenStreetMap)

`london.npz`, `manhattan.npz`: 640 m x 640 m, building heights rasterised at 1 m (`H[ix, iy]`), City of London around
Bank and Leadenhall Street (51.5133, -0.0835) and Midtown Manhattan around Bryant Park (40.7549, -73.9840). Buildings
without an OSM height tag are set to 12 m. Map data (c) OpenStreetMap contributors, Open Database Licence (ODbL),
https://www.openstreetmap.org/copyright. These derived rasters are distributed under the same licence.

The paper's city results use measured heights (Environment Agency LiDAR; NYC Building Footprints) for the same
footprints. Those rasters are not included in this deposit; the per-mission results computed with them are in
`results/`.

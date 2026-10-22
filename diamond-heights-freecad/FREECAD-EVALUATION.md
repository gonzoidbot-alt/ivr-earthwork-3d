# FreeCAD evaluation — Diamond Heights site modeling
Date: 2026-10-21 · FreeCAD 1.1.4 (brew cask), headless via `freecadcmd` · Scripts: `freecad/build_site.py`, `build_site_v2.py`

## What we did
1. Installed FreeCAD 1.1.4 via Homebrew cask (~700 MB, one command).
2. Parsed the Werx reports KMZ ("Diamond Heights Updated.kmz"): **474 georeferenced polylines across 29 layers** — eg_contour (127 rings), dg_grade_transition (95), eg_extrapolated_control (85), wall excavation control (60), restored ground, pond, tank pad, wall bottom/daylight, centerline, pavement/shoulder edges, tie-ins. KML z in meters → ×3.28084.
3. Built a full FreeCAD document headlessly (`freecadcmd`, no GUI): every layer as a named Part compound, plus EG terrain and DG design surfaces (radius-limited nearest-contour interpolation, 200×200 grid), saved `DiamondHeights_v2.fcstd` + OBJ exports of both surfaces. Runtime: ~2 minutes.
4. Ran surface-diff volumes on the interpolated surfaces and compared against our audited takeoff.

## Results
| Metric | FreeCAD surface diff | Audited pipeline (MC, N=4000) |
|---|---|---|
| Cut | 2,055 cy (v2 corridor-only) | 12,470–14,308 cy (p50 12,805) |
| Fill | 1,371,200 cy | 421–579 cy |
| Net | −1.37M cy (absurd) | +11,201 cy surplus p50 |

The naive surface diff is off by **three orders of magnitude**. Root cause is the DATA, not FreeCAD: the site is a two-bench canyon hillside (EG 2214→2444 ft), the KMZ's `dg_restored_ground_inferred` tie-ins are engineer extrapolations that float above existing grade across the slope, and any grid/IDW surface through them invents hundreds of thousands of cubic yards of phantom fill. Our audited pipeline reads the C-5/C-6/C-7 profile sheets station by station precisely to avoid this.

## FreeCAD as a tool — verdict
**Strengths (real):**
- **Headless automation is excellent.** `freecadcmd script.py` with full Python API, zero GUI. Install → working site model in one afternoon.
- **Engineering-grade geometry.** Part/Mesh workbenches, booleans, STEP/IGES/IFC export — the natural home for the tank pad, retaining wall and structural solids if IVR ever needs engineer-ready deliverables.
- **Free and open-source** — no license cost or seat management.
- Handles our data volume fine (474 polylines, 45k-facet mesh, no performance issues).

**Weaknesses (real):**
- **No civil/surface brain.** No TIN from breaklines, no corridor modeling, no station/offset primitives — civil 3D work means building the interpolation yourself. The bundled gmsh helps but isn't a surface-from-contours answer.
- **Wrong output for our client product.** The 3D visualizer is a Three.js web deliverable; FreeCAD's FCStd is opaque to browsers and its OBJ export adds nothing our mesh pipeline doesn't already produce.
- **Volume honesty is the same problem we already solved differently.** Exact solids would give exact volumes only if the design surfaces themselves were trustworthy — and the KMZ's inferred layers aren't.

**Recommendation:** keep FreeCAD installed as an offline engineering utility (solid modeling for pads/walls/structures, STEP hand-offs), **do not** move the site-model pipeline to it. The three.js visualizer fed by the KMZ line work + audited quantities stays the primary path. If IVR wants a PE-checkable deliverable later, FreeCAD is the right export target, fed by our existing geometry — not the modeling engine.

Artifacts: `DiamondHeights_v2.fcstd`, `EG_terrain_v2.obj`, `DG_design_v2.obj`, `site_map.png` (all layer linework), both build scripts.

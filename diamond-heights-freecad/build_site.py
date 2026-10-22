"""Build the Diamond Heights site model in FreeCAD (headless).
Inputs:  kml_layers.json (474 georeferenced design-model polylines, z in METERS).
Outputs: DiamondHeights.fcstd, DiamondHeights.obj (mesh export), report printed to stdout.

Coordinate frame: local FEET grid (x=East, y=North, z=elevation ft), origin at site min corner.
KML z values are meters -> x3.28084 per the Werx convention.
"""
import json, math, os
import FreeCAD as App
import Part, Mesh, MeshPart

SRC = "/Users/gonzo/projects/werx-takeoff/diamond-heights/freecad/kml_layers.json"
OUT = "/Users/gonzo/projects/werx-takeoff/diamond-heights/freecad"
M2FT = 3.28084
layers = json.load(open(SRC))

# local grid
allx = [p[0] for L in layers for p in L["pts"]]
ally = [p[1] for L in layers for p in L["pts"]]
x0, y0 = min(allx), min(ally)
def to_feet(p):
    lon, lat, zm = p
    x = (lon - x0) * 111320.0 * math.cos(math.radians(47.51)) * M2FT
    y = (lat - y0) * 110574.0 * M2FT
    z = zm * M2FT
    return (x, y, z)

doc = App.newDocument("DiamondHeights")

# --- 1. every layer as a named group of 3D polylines (Part wires) ---
import Draft
groups = {}
for L in layers:
    pts = [to_feet(p) for p in L["pts"]]
    if len(pts) < 2: continue
    g = groups.setdefault(L["layer"], [])
    try:
        shape = Part.makePolygon([App.Vector(*p) for p in pts])
        g.append(doc.addObject("Part::Feature", "wire").Shape if False else shape)
    except Exception as e:
        print("wire fail", L["layer"], e)
# add as one compound per layer, labelled
layer_report = []
for lname, shapes in groups.items():
    comp = Part.makeCompound(shapes)
    obj = doc.addObject("Part::Feature", "L_" + lname.replace("-", "_"))
    obj.Shape = comp
    obj.Label = lname
    layer_report.append((lname, len(shapes)))

# --- 2. EG terrain surface: Delaunay mesh over existing-grade contour points ---
eg_pts = []
for L in layers:
    if L["layer"].startswith("eg_"):
        eg_pts += [to_feet(p) for p in L["pts"]]
eg_pts = list(set(eg_pts))
print("EG points:", len(eg_pts))
eg_mesh = MeshPart.makePolygon(list(App.Vector(*p) for p in eg_pts)) if False else None
# Delaunay via Part (FreeCAD has no 2D Delaunay in Part; use Mesh.fillup? Use scipy-free approach:
# build a mesh from contour points with Mesh::Mesh() by triangulating consecutive contour rings instead:
# simpler robust route: build a Mesh from the sorted eg_contour rings as a faceted surface via inverse distance is heavy.
# Use gmsh (bundled) later if needed; for now triangulate with a simple grid interpolation.
# --- grid the EG surface by IDW from contour points, then mesh the grid ---
gx0, gy0 = 0, 0
gx1 = max(p[0] for p in eg_pts); gy1 = max(p[1] for p in eg_pts)
nx, ny = 160, 160
dx, dy = (gx1-gx0)/nx, (gy1-gy0)/ny
grid = []
eg_arr = eg_pts
def idw(x, y, k=8):
    ds = sorted(((xx-x)**2+(yy-y)**2, zz) for xx, yy, zz in eg_arr)
    top = ds[:k]
    wsum = sum(1/(d+1e-6) for d, _ in top)
    return sum(zz/(d+1e-6) for d, zz in top)/wsum
verts = []
for j in range(ny+1):
    for i in range(nx+1):
        x, y = gx0+i*dx, gy0+j*dy
        verts.append((x, y, idw(x, y)))
faces = []
vid = lambda i, j: j*(nx+1)+i
for j in range(ny):
    for i in range(nx):
        faces.append((vid(i,j), vid(i+1,j), vid(i,j+1)))
        faces.append((vid(i+1,j), vid(i+1,j+1), vid(i,j+1)))
m = Mesh.Mesh()
m.addFacets([(App.Vector(*verts[a]), App.Vector(*verts[b]), App.Vector(*verts[c])) for a,b,c in faces])
eg_obj = doc.addObject("Mesh::Feature", "EG_terrain_IDW")
eg_obj.Mesh = m
print("EG grid mesh:", len(m.Facets), "facets")

# --- 3. DG design surface from restored-ground + grade-transition points (same IDW grid) ---
dg_pts = []
for L in layers:
    if L["layer"].startswith("dg_"):
        dg_pts += [to_feet(p) for p in L["pts"]]
dg_pts = list(set(dg_pts))
def idw_dg(x, y, k=8):
    ds = sorted(((xx-x)**2+(yy-y)**2, zz) for xx, yy, zz in dg_pts)
    top = ds[:k]
    wsum = sum(1/(d+1e-6) for d, _ in top)
    return sum(zz/(d+e-6) if False else zz/(d+1e-6) for d, zz in top)/wsum
dverts = []
for j in range(ny+1):
    for i in range(nx+1):
        x, y = gx0+i*dx, gy0+j*dy
        dverts.append((x, y, idw_dg(x, y)))
dfaces = []
for j in range(ny):
    for i in range(nx):
        dfaces.append((vid(i,j), vid(i+1,j), vid(i,j+1)))
        dfaces.append((vid(i+1,j), vid(i+1,j+1), vid(i,j+1)))
dm = Mesh.Mesh()
dm.addFacets([(App.Vector(*dverts[a]), App.Vector(*dverts[b]), App.Vector(*dverts[c])) for a,b,c in dfaces])
dg_obj = doc.addObject("Mesh::Feature", "DG_design_IDW")
dg_obj.Mesh = dm
print("DG grid mesh:", len(dm.Facets), "facets")

# --- 4. quick cut/fill cross-check on the same grid (cell 3D diff, ft3 -> cy) ---
cut = fill = 0.0
cell_area = dx*dy
for j in range(0, ny+1):
    for i in range(0, nx+1):
        k = vid(i,j)
        d = verts[k][2] - dverts[k][2]   # EG - DG: positive = cut
        if d > 0: cut += d
        else: fill += -d
cut_cy = cut * cell_area / 27.0
fill_cy = fill * cell_area / 27.0
print(f"IDW-grid cut/fill: cut {cut_cy:,.0f} cy, fill {fill_cy:,.0f} cy, net {cut_cy-fill_cy:,.0f} cy")

# --- 5. export ---
import Mesh
doc.recompute()
doc.saveAs(os.path.join(OUT, "DiamondHeights.fcstd"))
eg_obj.Mesh.write(os.path.join(OUT, "EG_terrain.obj"))
dg_obj.Mesh.write(os.path.join(OUT, "DG_design.obj"))
print("saved:", os.path.join(OUT, "DiamondHeights.fcstd"))
print("LAYERS:")
for lname, n in sorted(layer_report, key=lambda t: -t[1]):
    print(f"  {lname}: {n} polylines")
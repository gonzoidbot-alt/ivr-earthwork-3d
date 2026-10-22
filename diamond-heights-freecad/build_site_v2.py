"""v2: corridor-restricted surfaces with radius-limited nearest-contour interpolation.
Only compares where BOTH surfaces are defined (within 25 ft of supporting data)."""
import json, math, os
import FreeCAD as App
import Mesh

SRC = "/Users/gonzo/projects/werx-takeoff/diamond-heights/freecad/kml_layers.json"
OUT = "/Users/gonzo/projects/werx-takeoff/diamond-heights/freecad"
M2FT = 3.28084
layers = json.load(open(SRC))
allx = [p[0] for L in layers for p in L["pts"]]
ally = [p[1] for L in layers for p in L["pts"]]
x0, y0 = min(allx), min(ally)
def to_feet(p):
    lon, lat, zm = p
    return ((lon-x0)*111320.0*math.cos(math.radians(47.51))*M2FT,
            (lat-y0)*110574.0*M2FT, zm*M2FT)

doc = App.newDocument("DiamondHeights2")

def segments_of(layer_prefixes):
    segs = []
    for L in layers:
        if any(L["layer"].startswith(p) for p in layer_prefixes):
            pts = [to_feet(p) for p in L["pts"]]
            for a, b in zip(pts, pts[1:]):
                segs.append((a, b))
    return segs

def make_surface(segs, name, radius=25.0, nx=200, ny=200):
    # grid value = inverse-distance over sample points ON segments within radius; None if none
    allx = [p[0] for a,b in segs for p in (a,b)]
    ally = [p[1] for a,b in segs for p in (a,b)]
    x0g, y0g, x1g, y1g = min(allx), min(ally), max(allx), max(ally)
    dx, dy = (x1g-x0g)/nx, (y1g-y0g)/ny
    # bucket segments into a coarse grid for speed
    import collections
    cell = max(dx, dy)*4
    buckets = collections.defaultdict(list)
    for a, b in segs:
        for cx in range(int(a[0]//cell), int(b[0]//cell)+1):
            for cy in range(int(min(a[1],b[1])//cell), int(max(a[1],b[1])//cell)+1):
                buckets[(cx, cy)].append((a, b))
    def val(x, y):
        cands = []
        cx, cy = int(x//cell), int(y//cell)
        for i in (-1,0,1):
            for j in (-1,0,1):
                cands += buckets.get((cx+i, cy+j), [])
        best = []
        for a, b in cands:
            ax, ay, az = a; bx, by, bz = b
            ex, ey = bx-ax, by-ay
            L2 = ex*ex+ey*ey
            t = 0.0 if L2 == 0 else max(0.0, min(1.0, ((x-ax)*ex+(y-ay)*ey)/L2))
            px, py = ax+t*ex, ay+t*ey
            d2 = (px-x)**2 + (py-y)**2
            if d2 <= radius*radius:
                best.append((d2, az + t*(bz-az)))
        if not best: return None
        w = sum(1/(d+0.5) for d, _ in best)
        return sum(z/(d+0.5) for d, z in best)/w
    verts = []
    defined = []
    for j in range(ny+1):
        row = []
        for i in range(nx+1):
            v = val(x0g+i*dx, y0g+j*dy)
            row.append(v)
        verts.append(row)
    # mesh only cells where all 4 corners defined
    mesh = Mesh.Mesh()
    nf = 0
    for j in range(ny):
        for i in range(nx):
            c = [verts[j][i], verts[j][i+1], verts[j+1][i], verts[j+1][i+1]]
            if any(v is None for v in c): continue
            def P(k): return App.Vector(x0g+i*dx + (dx if k in (1,3) else 0), y0g+j*dy + (dy if k in (2,3) else 0), c[k])
            mesh.addFacets([(P(0),P(1),P(2)), (P(1),P(3),P(2))]); nf += 2
    obj = doc.addObject("Mesh::Feature", name)
    obj.Mesh = mesh
    print(f"{name}: {nf} facets ({nx}x{ny} grid), extent {x1g-x0g:.0f} x {y1g-y0g:.0f} ft")
    return obj, verts, (x0g, y0g, dx, dy, nx, ny)

eg_segs = segments_of(["eg_contour", "eg_extrapolated_control", "eg_terrain_breakline"])
dg_segs = segments_of(["dg_restored_ground", "dg_restored_ground_inferred", "dg_grade_transition",
                       "dg_ditch_edge", "dg_ditch_flowline", "dg_pond_bottom", "dg_pond_rim",
                       "str_tank_pad", "str_wall_01_bottomface", "dg_tiein_daylight"])
eg_obj, egv, gmeta = make_surface(eg_segs, "EG_terrain_radius25")
dg_obj, dgv, _ = make_surface(dg_segs, "DG_design_radius25")

# cut/fill only where both defined
(x0g, y0g, dx, dy, nx, ny) = gmeta
cut = fill = 0.0; area = 0.0; cells = 0
for j in range(ny+1):
    for i in range(nx+1):
        e, d = egv[j][i], dgv[j][i]
        if e is None or d is None: continue
        delta = e - d
        if delta > 0: cut += delta
        else: fill += -delta
        area += dx*dy; cells += 1
print(f"defined cells: {cells} ({area/43560:.1f} acres)")
print(f"cut {cut*area/max(cells,1)/27* (nx+1)*(ny+1)/max(cells,1):,.0f}")  # placeholder corrected below
# proper: sum per-cell then scale by defined fraction
cut_cy = cut*dx*dy/27*(nx+1)*(ny+1)/max(cells,1)
fill_cy = fill*dx*dy/27*(nx+1)*(ny+1)/max(cells,1)
print(f"corridor cut/fill: cut {cut_cy:,.0f} cy, fill {fill_cy:,.0f} cy, net {cut_cy-fill_cy:,.0f} cy")

doc.recompute()
doc.saveAs(os.path.join(OUT, "DiamondHeights_v2.fcstd"))
eg_obj.Mesh.write(os.path.join(OUT, "EG_terrain_v2.obj"))
dg_obj.Mesh.write(os.path.join(OUT, "DG_design_v2.obj"))
print("saved DiamondHeights_v2.fcstd")
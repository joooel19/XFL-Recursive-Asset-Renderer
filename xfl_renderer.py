#!/usr/bin/env python3
"""
SC / XFL Recursive Asset Renderer CLI v3.3
------------------------------------------
Recursively parses Supercell (.sc) / Adobe Flash XFL projects and renders:
  - Clean Static PNGs
  - Transparent Animated GIFs (crisp 1-bit alpha quantization)
  - 32-bit TrueColor APNGs (Animated PNGs)
  - PNG Frame Sequences (optional via --export-frames)
  - HTML5 Canvas JS Real-Time Player & Web Export (via --export-js)
  - Interactive HTML Gallery Dashboard

Pure In-Memory Archive Processing:
  - Reads .fla and .zip files 100% in-memory without unpacking to disk!
  - Also supports unpacked directories (containing LIBRARY/)

Organized Output Folder Structure:
  output/
    ├── static/                # Single-frame PNG assets & covers
    ├── animations_gif/        # Transparent animated GIFs
    ├── animations_apng/       # High-quality Animated PNGs
    ├── web_js_player/         # HTML5 Canvas real-time JS player & animation data (via --export-js)
    ├── frame_sequences/       # PNG frame sequences (via --export-frames)
    └── index.html             # Interactive HTML Web Gallery
"""

import os
import sys
import io
import glob
import math
import json
import zipfile
import argparse
import xml.etree.ElementTree as ET
from PIL import Image

class Matrix:
    """2D Affine Transformation Matrix: [a, c, tx, b, d, ty]"""
    def __init__(self, a=1.0, b=0.0, c=0.0, d=1.0, tx=0.0, ty=0.0):
        self.a = float(a)
        self.b = float(b)
        self.c = float(c)
        self.d = float(d)
        self.tx = float(tx)
        self.ty = float(ty)

    def multiply(self, child):
        a = self.a * child.a + self.c * child.b
        b = self.b * child.a + self.d * child.b
        c = self.a * child.c + self.c * child.d
        d = self.b * child.c + self.d * child.d
        tx = self.a * child.tx + self.c * child.ty + self.tx
        ty = self.b * child.tx + self.d * child.ty + self.ty
        return Matrix(a, b, c, d, tx, ty)

    def transform_point(self, x, y):
        nx = self.a * x + self.c * y + self.tx
        ny = self.b * x + self.d * y + self.ty
        return nx, ny

    def get_inverse_tuple(self):
        det = self.a * self.d - self.b * self.c
        if abs(det) < 1e-9:
            return None
        inv_a = self.d / det
        inv_c = -self.c / det
        inv_b = -self.b / det
        inv_d = self.a / det

        A = inv_a
        B = inv_c
        C = -inv_a * self.tx - inv_c * self.ty
        D = inv_b
        E = inv_d
        F = -inv_b * self.tx - inv_d * self.ty
        return (A, B, C, D, E, F)

class ColorTransform:
    """Color Transform multipliers and offsets"""
    def __init__(self, rm=1.0, gm=1.0, bm=1.0, am=1.0, ro=0, go=0, bo=0, ao=0):
        self.rm = float(rm)
        self.gm = float(gm)
        self.bm = float(bm)
        self.am = float(am)
        self.ro = float(ro)
        self.go = float(go)
        self.bo = float(bo)
        self.ao = float(ao)

    def multiply(self, child):
        return ColorTransform(
            self.rm * child.rm,
            self.gm * child.gm,
            self.bm * child.bm,
            self.am * child.am,
            self.ro + child.ro * self.rm,
            self.go + child.go * self.gm,
            self.bo + child.bo * self.bm,
            self.ao + child.ao * self.am
        )

class XFLParser:
    def __init__(self, input_path):
        self.input_path = input_path
        self.zip_file = None
        self.library_prefix = "LIBRARY/"
        self.symbol_cache = {}
        self.bitmap_cache = {}
        self.is_archive = False

        if os.path.isfile(input_path) and input_path.lower().endswith(('.fla', '.zip')):
            self.is_archive = True
            self.zip_file = zipfile.ZipFile(input_path, 'r')
            namelist = [n.replace('\\', '/') for n in self.zip_file.namelist()]
            for name in namelist:
                if "LIBRARY/" in name:
                    self.library_prefix = name[:name.index("LIBRARY/") + len("LIBRARY/")]
                    break
        elif os.path.isdir(input_path):
            if not os.path.exists(os.path.join(input_path, "LIBRARY")):
                subdirs = [os.path.join(input_path, d) for d in os.listdir(input_path) if os.path.isdir(os.path.join(input_path, d))]
                for sd in subdirs:
                    if os.path.exists(os.path.join(sd, "LIBRARY")):
                        self.input_path = sd
                        break

    def get_export_names(self):
        """Returns list of export symbol names (e.g. ['exports/floating_trunk1', ...])"""
        export_names = []
        if self.is_archive:
            exports_prefix = self.library_prefix + "exports/"
            for name in self.zip_file.namelist():
                norm = name.replace("\\", "/")
                if norm.startswith(exports_prefix) and norm.endswith(".xml"):
                    rel = norm[len(self.library_prefix):-4]
                    export_names.append(rel)
        else:
            exports_dir = os.path.join(self.input_path, "LIBRARY", "exports")
            if os.path.exists(exports_dir):
                for f in glob.glob(os.path.join(exports_dir, "*.xml")):
                    filename = os.path.basename(f)
                    export_names.append(f"exports/{os.path.splitext(filename)[0]}")
        return export_names

    def load_symbol(self, item_name):
        rel_path = item_name.replace("\\", "/").strip("/")
        if not rel_path.endswith(".xml"):
            rel_path += ".xml"

        if rel_path in self.symbol_cache:
            return self.symbol_cache[rel_path]

        if self.is_archive:
            zip_entry = self.library_prefix + rel_path
            try:
                data = self.zip_file.read(zip_entry)
                root = ET.fromstring(data)
                self.symbol_cache[rel_path] = root
                return root
            except Exception:
                self.symbol_cache[rel_path] = None
                return None
        else:
            xml_path = os.path.join(self.input_path, "LIBRARY", rel_path)
            if not os.path.exists(xml_path):
                self.symbol_cache[rel_path] = None
                return None
            try:
                tree = ET.parse(xml_path)
                root = tree.getroot()
                self.symbol_cache[rel_path] = root
                return root
            except Exception:
                self.symbol_cache[rel_path] = None
                return None

    def get_bitmap_image(self, item_name):
        rel_path = item_name.replace("\\", "/").strip("/")
        if not rel_path.endswith(".png"):
            rel_path += ".png"

        if rel_path in self.bitmap_cache:
            return self.bitmap_cache[rel_path]

        if self.is_archive:
            zip_entry = self.library_prefix + rel_path
            try:
                data = self.zip_file.read(zip_entry)
                img = Image.open(io.BytesIO(data)).convert("RGBA")
                self.bitmap_cache[rel_path] = img
                return img
            except Exception:
                self.bitmap_cache[rel_path] = None
                return None
        else:
            png_path = os.path.join(self.input_path, "LIBRARY", rel_path)
            if not os.path.exists(png_path):
                self.bitmap_cache[rel_path] = None
                return None
            try:
                img = Image.open(png_path).convert("RGBA")
                self.bitmap_cache[rel_path] = img
                return img
            except Exception:
                self.bitmap_cache[rel_path] = None
                return None

    def parse_matrix(self, elem):
        mat_elem = elem.find("{http://ns.adobe.com/xfl/2008/}matrix/{http://ns.adobe.com/xfl/2008/}Matrix")
        if mat_elem is None:
            mat_elem = elem.find(".//Matrix")
        if mat_elem is None:
            return Matrix()
        
        a = mat_elem.attrib.get("a", 1.0)
        b = mat_elem.attrib.get("b", 0.0)
        c = mat_elem.attrib.get("c", 0.0)
        d = mat_elem.attrib.get("d", 1.0)
        tx = mat_elem.attrib.get("tx", 0.0)
        ty = mat_elem.attrib.get("ty", 0.0)
        return Matrix(a, b, c, d, tx, ty)

    def parse_color(self, elem):
        col_elem = elem.find("{http://ns.adobe.com/xfl/2008/}color/{http://ns.adobe.com/xfl/2008/}Color")
        if col_elem is None:
            col_elem = elem.find(".//Color")
        if col_elem is None:
            return ColorTransform()
        
        rm = col_elem.attrib.get("redMultiplier", 1.0)
        gm = col_elem.attrib.get("greenMultiplier", 1.0)
        bm = col_elem.attrib.get("blueMultiplier", 1.0)
        am = col_elem.attrib.get("alphaMultiplier", 1.0)
        ro = col_elem.attrib.get("redOffset", 0)
        go = col_elem.attrib.get("greenOffset", 0)
        bo = col_elem.attrib.get("blueOffset", 0)
        ao = col_elem.attrib.get("alphaOffset", 0)
        return ColorTransform(rm, gm, bm, am, ro, go, bo, ao)

    def get_symbol_duration(self, root):
        if root is None:
            return 1
        max_frame = 1
        for layer in root.iter():
            if layer.tag.endswith("DOMLayer"):
                curr = 0
                for frame in layer.iter():
                    if frame.tag.endswith("DOMFrame"):
                        idx = int(frame.attrib.get("index", curr))
                        dur = int(frame.attrib.get("duration", 1))
                        if idx + dur > max_frame:
                            max_frame = idx + dur
                        curr = idx + dur
        return max_frame

    def get_leaf_bitmaps(self, item_name, frame_index=0, parent_matrix=None, parent_color=None, depth=0):
        if parent_matrix is None:
            parent_matrix = Matrix()
        if parent_color is None:
            parent_color = ColorTransform()

        if depth > 30:
            return []

        root = self.load_symbol(item_name)
        if root is None:
            return []

        leaf_bitmaps = []
        layers = [elem for elem in root.iter() if elem.tag.endswith("DOMLayer")]

        for layer in reversed(layers):
            target_frame = None
            curr = 0
            for frame in layer.iter():
                if frame.tag.endswith("DOMFrame"):
                    idx = int(frame.attrib.get("index", curr))
                    dur = int(frame.attrib.get("duration", 1))
                    curr = idx + dur
                    if idx <= frame_index < idx + dur:
                        target_frame = frame
                        break
            
            if target_frame is None:
                continue

            for child in target_frame.iter():
                tag = child.tag.split("}")[-1]
                if tag == "DOMSymbolInstance":
                    child_item = child.attrib.get("libraryItemName")
                    if not child_item:
                        continue
                    m = self.parse_matrix(child)
                    c = self.parse_color(child)
                    combined_m = parent_matrix.multiply(m)
                    combined_c = parent_color.multiply(c)

                    child_root = self.load_symbol(child_item)
                    child_dur = self.get_symbol_duration(child_root)
                    child_frame_idx = frame_index % child_dur if child_dur > 0 else 0

                    sub_bitmaps = self.get_leaf_bitmaps(
                        child_item,
                        frame_index=child_frame_idx,
                        parent_matrix=combined_m,
                        parent_color=combined_c,
                        depth=depth + 1
                    )
                    leaf_bitmaps.extend(sub_bitmaps)

                elif tag == "DOMBitmapInstance":
                    child_item = child.attrib.get("libraryItemName")
                    if not child_item:
                        continue
                    m = self.parse_matrix(child)
                    c = self.parse_color(child)
                    combined_m = parent_matrix.multiply(m)
                    combined_c = parent_color.multiply(c)

                    img = self.get_bitmap_image(child_item)
                    if img:
                        leaf_bitmaps.append({
                            "name": child_item,
                            "image": img,
                            "matrix": combined_m,
                            "color": combined_c
                        })

        return leaf_bitmaps

    def close(self):
        if self.zip_file:
            self.zip_file.close()

def compute_global_bounds(leaf_bitmaps_sequence):
    min_x, min_y = float('inf'), float('inf')
    max_x, max_y = float('-inf'), float('-inf')
    has_data = False

    for leafs in leaf_bitmaps_sequence:
        for item in leafs:
            has_data = True
            img = item["image"]
            w, h = img.size
            m = item["matrix"]
            pts = [
                m.transform_point(0, 0),
                m.transform_point(w, 0),
                m.transform_point(w, h),
                m.transform_point(0, h)
            ]
            for px, py in pts:
                if px < min_x: min_x = px
                if py < min_y: min_y = py
                if px > max_x: max_x = px
                if py > max_y: max_y = py

    if not has_data:
        return (0, 0, 100, 100)
    return (min_x, min_y, max_x, max_y)

def apply_color_transform(img, color):
    if color.rm == 1.0 and color.gm == 1.0 and color.bm == 1.0 and color.am == 1.0 and \
       color.ro == 0 and color.go == 0 and color.bo == 0 and color.ao == 0:
        return img
    
    r, g, b, a = img.split()
    r = r.point(lambda p: min(255, max(0, int(p * color.rm + color.ro))))
    g = g.point(lambda p: min(255, max(0, int(p * color.gm + color.go))))
    b = b.point(lambda p: min(255, max(0, int(p * color.bm + color.bo))))
    a = a.point(lambda p: min(255, max(0, int(p * color.am + color.ao))))
    return Image.merge("RGBA", (r, g, b, a))

def render_frame(leaf_bitmaps, bounds, margin=10, scale=1.0):
    min_x, min_y, max_x, max_y = bounds
    canvas_w = int(math.ceil((max_x - min_x) * scale)) + int(2 * margin * scale)
    canvas_h = int(math.ceil((max_y - min_y) * scale)) + int(2 * margin * scale)
    canvas_w = max(1, canvas_w)
    canvas_h = max(1, canvas_h)

    canvas = Image.new("RGBA", (canvas_w, canvas_h), (0, 0, 0, 0))

    for item in leaf_bitmaps:
        raw_img = item["image"]
        color_img = apply_color_transform(raw_img, item["color"])
        m = item["matrix"]

        tx_canvas = (m.tx - min_x + margin) * scale
        ty_canvas = (m.ty - min_y + margin) * scale
        
        m_canvas = Matrix(
            m.a * scale, m.b * scale,
            m.c * scale, m.d * scale,
            tx_canvas, ty_canvas
        )
        inv_tuple = m_canvas.get_inverse_tuple()
        if inv_tuple is None:
            continue

        transformed_img = color_img.transform(
            (canvas_w, canvas_h),
            Image.AFFINE,
            inv_tuple,
            resample=Image.BILINEAR
        )
        canvas.alpha_composite(transformed_img)

    return canvas

def convert_rgba_to_clean_gif_frame(rgba_img):
    alpha = rgba_img.split()[3]
    rgb = rgba_img.convert('RGB')
    p_img = rgb.convert('P', palette=Image.ADAPTIVE, colors=255)
    mask = Image.eval(alpha, lambda a: 255 if a < 128 else 0)
    p_img.paste(255, mask)
    p_img.info['transparency'] = 255
    return p_img

def save_clean_gif(rendered_frames, gif_path, fps=30):
    p_frames = [convert_rgba_to_clean_gif_frame(f) for f in rendered_frames]
    p_frames[0].save(
        gif_path,
        save_all=True,
        append_images=p_frames[1:],
        duration=int(1000 / fps),
        loop=0,
        disposal=2
    )

def generate_js_player_export(output_dir, symbols_data, parser):
    """Exports HTML5 Canvas JS player with embedded animations_data.js (CORS-safe for local file:// opening)"""
    js_dir = os.path.join(output_dir, "web_js_player")
    textures_dir = os.path.join(js_dir, "textures")
    os.makedirs(textures_dir, exist_ok=True)

    used_textures = set()
    for sym in symbols_data:
        for frame in sym["sequence_data"]:
            for elem in frame:
                used_textures.add(elem["name"])

    for tex in used_textures:
        img = parser.get_bitmap_image(tex)
        if img:
            tex_filename = os.path.basename(tex) + ".png"
            img.save(os.path.join(textures_dir, tex_filename), "PNG")

    manifest = {}
    for sym in symbols_data:
        name = sym["name"]
        bounds = sym["bounds"]
        margin = 10
        width = int(math.ceil(bounds[2] - bounds[0])) + 2 * margin
        height = int(math.ceil(bounds[3] - bounds[1])) + 2 * margin
        
        frames_json = []
        for frame in sym["sequence_data"]:
            elements_json = []
            for elem in frame:
                m = elem["matrix"]
                c = elem["color"]
                elements_json.append({
                    "src": "textures/" + os.path.basename(elem["name"]) + ".png",
                    "matrix": [m.a, m.b, m.c, m.d, m.tx - bounds[0] + margin, m.ty - bounds[1] + margin],
                    "alpha": c.am
                })
            frames_json.append(elements_json)

        manifest[name] = {
            "width": width,
            "height": height,
            "duration": sym["duration"],
            "frames": frames_json
        }

    js_content = "window.ANIMATION_DATA = " + json.dumps(manifest, indent=2) + ";"
    with open(os.path.join(js_dir, "animations_data.js"), "w", encoding="utf-8") as f:
        f.write(js_content)

    player_html = """<!DOCTYPE html>
<html lang="de">
<head>
    <meta charset="UTF-8">
    <title>HTML5 Canvas Real-Time Player</title>
    <link href="https://fonts.googleapis.com/css2?family=Outfit:wght@400;600;700&display=swap" rel="stylesheet">
    <style>
        body { font-family: 'Outfit', sans-serif; background: #0b0f19; color: #f3f4f6; padding: 30px; text-align: center; }
        h1 { color: #60a5fa; margin-bottom: 10px; }
        p { color: #9ca3af; margin-bottom: 20px; }
        .canvas-container { background: #161b26; border: 1px solid #252e42; border-radius: 12px; padding: 20px; display: inline-block; }
        canvas { background-image: radial-gradient(#262f45 1px, transparent 1px); background-size: 10px 10px; border-radius: 8px; margin-top: 10px; }
        select { background: #1f293d; color: white; padding: 8px 16px; border-radius: 6px; border: 1px solid #3b82f6; margin-bottom: 15px; font-size: 14px; cursor: pointer; }
    </style>
</head>
<body>
    <h1>Echtzeit HTML5 Canvas Animation (60 FPS)</h1>
    <p>Rendert Flash/SC Matrizen & Ebenen direkt auf der GPU des Browsers.</p>

    <div class="canvas-container">
        <div><select id="animSelect"></select></div>
        <canvas id="stage"></canvas>
    </div>

    <script src="animations_data.js"></script>
    <script>
        const manifest = window.ANIMATION_DATA || {};
        const imageCache = {};
        let currentAnim = null;
        let currentFrame = 0;
        let fps = 30;
        let lastTime = 0;

        const canvas = document.getElementById('stage');
        const ctx = canvas.getContext('2d');
        const select = document.getElementById('animSelect');

        async function init() {
            const texUrls = new Set();
            for (const name in manifest) {
                manifest[name].frames.forEach(fr => fr.forEach(el => texUrls.add(el.src)));
            }

            await Promise.all(Array.from(texUrls).map(src => new Promise(resolve => {
                const img = new Image();
                img.onload = () => { imageCache[src] = img; resolve(); };
                img.onerror = () => { console.error("Error loading texture:", src); resolve(); };
                img.src = src;
            })));

            for (const name in manifest) {
                const opt = document.createElement('option');
                opt.value = name;
                opt.textContent = name;
                select.appendChild(opt);
            }

            select.onchange = () => playAnimation(select.value);
            if (Object.keys(manifest).length > 0) playAnimation(Object.keys(manifest)[0]);

            requestAnimationFrame(loop);
        }

        function playAnimation(name) {
            currentAnim = manifest[name];
            currentFrame = 0;
            canvas.width = currentAnim.width;
            canvas.height = currentAnim.height;
        }

        function loop(timestamp) {
            requestAnimationFrame(loop);
            if (!currentAnim) return;

            if (timestamp - lastTime > 1000 / fps) {
                lastTime = timestamp;
                drawFrame(currentAnim.frames[currentFrame]);
                currentFrame = (currentFrame + 1) % currentAnim.frames.length;
            }
        }

        function drawFrame(elements) {
            ctx.clearRect(0, 0, canvas.width, canvas.height);
            for (const el of elements) {
                const img = imageCache[el.src];
                if (!img) continue;

                ctx.save();
                ctx.globalAlpha = el.alpha !== undefined ? el.alpha : 1.0;
                const [a, b, c, d, tx, ty] = el.matrix;
                ctx.transform(a, b, c, d, tx, ty);
                ctx.drawImage(img, 0, 0);
                ctx.restore();
            }
        }

        init();
    </script>
</body>
</html>
"""
    with open(os.path.join(js_dir, "player.html"), "w", encoding="utf-8") as f:
        f.write(player_html)

    print(f"Generated HTML5 Canvas JS Real-Time Player in: {js_dir}")

def generate_html_gallery(output_dir, items_data):
    html_content = """<!DOCTYPE html>
<html lang="de">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>SC / XFL Asset Viewer</title>
    <link href="https://fonts.googleapis.com/css2?family=Outfit:wght@400;600;700&display=swap" rel="stylesheet">
    <style>
        :root { --bg-color: #0b0f19; --card-bg: #161b26; --card-border: #252e42; --accent: #3b82f6; --text-main: #f3f4f6; --text-sub: #9ca3af; }
        * { box-sizing: border-box; margin: 0; padding: 0; }
        body { font-family: 'Outfit', sans-serif; background-color: var(--bg-color); color: var(--text-main); padding: 30px; }
        header { margin-bottom: 30px; display: flex; justify-content: space-between; align-items: center; border-bottom: 1px solid var(--card-border); padding-bottom: 20px; }
        h1 { font-size: 28px; font-weight: 700; background: linear-gradient(135deg, #60a5fa, #a855f7); -webkit-background-clip: text; -webkit-text-fill-color: transparent; }
        .stats { color: var(--text-sub); font-size: 14px; }
        .grid { display: grid; grid-template-columns: repeat(auto-fill, minmax(260px, 1fr)); gap: 20px; }
        .card { background: var(--card-bg); border: 1px solid var(--card-border); border-radius: 12px; padding: 16px; display: flex; flex-direction: column; align-items: center; transition: transform 0.2s, border-color 0.2s; }
        .card:hover { transform: translateY(-4px); border-color: var(--accent); }
        .preview-box { width: 100%; height: 180px; background-image: radial-gradient(#262f45 1px, transparent 1px); background-size: 12px 12px; border-radius: 8px; display: flex; align-items: center; justify-content: center; overflow: hidden; margin-bottom: 12px; }
        .preview-box img { max-width: 90%; max-height: 90%; object-fit: contain; }
        .item-title { font-weight: 600; font-size: 15px; margin-bottom: 4px; text-align: center; word-break: break-all; }
        .item-meta { font-size: 12px; color: var(--text-sub); margin-bottom: 12px; }
        .links { display: flex; gap: 8px; flex-wrap: wrap; justify-content: center; }
        .badge { font-size: 11px; padding: 4px 8px; border-radius: 6px; background: #1f293d; color: #93c5fd; text-decoration: none; transition: background 0.2s; }
        .badge:hover { background: var(--accent); color: white; }
    </style>
</head>
<body>
    <header>
        <div>
            <h1>SC Asset Viewer</h1>
            <p class="stats">Entpackte & Gerenderte Grafiken</p>
        </div>
        <div class="stats">Gerenderte Assets: ''' + str(len(items_data)) + '''</div>
    </header>
    <div class="grid">
"""
    for item in items_data:
        name, dur, rel_preview = item["name"], item["duration"], item["preview_rel"]
        html_content += f"""
        <div class="card">
            <div class="preview-box"><img src="{rel_preview}" alt="{name}"></div>
            <div class="item-title">{name}</div>
            <div class="item-meta">Dauer: {dur} Frame(s)</div>
            <div class="links">
"""
        for f in item["files_rel"]:
            html_content += f'<a class="badge" href="{f["path"]}" target="_blank">{f["type"].upper()}</a>'
        html_content += "</div></div>"

    html_content += "</div></body></html>"
    index_path = os.path.join(output_dir, "index.html")
    with open(index_path, "w", encoding="utf-8") as f:
        f.write(html_content)
    print(f"Generated Web Gallery Dashboard: {index_path}")

def render_project(input_path, output_dir, fps=30, scale=1.0, formats=["png", "gif", "apng"], limit=None, export_frames=False, export_js=False):
    parser = XFLParser(input_path)
    export_names = parser.get_export_names()

    if not export_names:
        print(f"Error: No export symbols found in input: {input_path}")
        parser.close()
        return

    try:
        dir_static = os.path.join(output_dir, "static")
        dir_gif = os.path.join(output_dir, "animations_gif")
        dir_apng = os.path.join(output_dir, "animations_apng")
        dir_seq = os.path.join(output_dir, "frame_sequences")

        os.makedirs(dir_static, exist_ok=True)
        if "gif" in formats: os.makedirs(dir_gif, exist_ok=True)
        if "apng" in formats: os.makedirs(dir_apng, exist_ok=True)
        if export_frames or "frames" in formats: os.makedirs(dir_seq, exist_ok=True)

        if limit is not None and limit > 0:
            export_names = export_names[:limit]
            print(f"Limiting render to first {limit} export item(s)...")

        print(f"Rendering {len(export_names)} export items from {input_path}")
        gallery_items = []
        js_export_symbols = []

        for idx, item_name in enumerate(export_names, 1):
            symbol_name = item_name.split("/")[-1]

            root = parser.load_symbol(item_name)
            duration = parser.get_symbol_duration(root)

            print(f"[{idx}/{len(export_names)}] Rendering '{symbol_name}' ({duration} frames)...")

            sequence = [parser.get_leaf_bitmaps(item_name, frame_index=f) for f in range(duration)]
            bounds = compute_global_bounds(sequence)
            rendered_frames = [render_frame(sequence[f], bounds, margin=10, scale=scale) for f in range(duration)]

            js_export_symbols.append({
                "name": symbol_name,
                "duration": duration,
                "bounds": bounds,
                "sequence_data": sequence
            })

            item_gallery = {"name": symbol_name, "duration": duration, "preview_rel": "", "files_rel": []}

            if duration == 1:
                png_path = os.path.join(dir_static, f"{symbol_name}.png")
                rendered_frames[0].save(png_path, "PNG")
                item_gallery["preview_rel"] = f"static/{symbol_name}.png"
                item_gallery["files_rel"].append({"type": "png", "path": f"static/{symbol_name}.png"})
            else:
                preview_png = os.path.join(dir_static, f"{symbol_name}_cover.png")
                rendered_frames[0].save(preview_png, "PNG")
                item_gallery["preview_rel"] = f"static/{symbol_name}_cover.png"
                item_gallery["files_rel"].append({"type": "png", "path": f"static/{symbol_name}_cover.png"})

                if "gif" in formats:
                    gif_path = os.path.join(dir_gif, f"{symbol_name}.gif")
                    save_clean_gif(rendered_frames, gif_path, fps=fps)
                    item_gallery["files_rel"].append({"type": "gif", "path": f"animations_gif/{symbol_name}.gif"})

                if "apng" in formats:
                    apng_path = os.path.join(dir_apng, f"{symbol_name}.png")
                    rendered_frames[0].save(
                        apng_path,
                        save_all=True, append_images=rendered_frames[1:], duration=int(1000/fps), loop=0
                    )
                    item_gallery["files_rel"].append({"type": "apng", "path": f"animations_apng/{symbol_name}.png"})

                if export_frames or "frames" in formats:
                    seq_folder = os.path.join(dir_seq, symbol_name)
                    os.makedirs(seq_folder, exist_ok=True)
                    for f_idx, f_img in enumerate(rendered_frames):
                        f_img.save(os.path.join(seq_folder, f"frame_{f_idx:03d}.png"), "PNG")
                    item_gallery["files_rel"].append({"type": "frames", "path": f"frame_sequences/{symbol_name}/"})

            gallery_items.append(item_gallery)

        if export_js:
            generate_js_player_export(output_dir, js_export_symbols, parser)

        generate_html_gallery(output_dir, gallery_items)
        print(f"\nRender-Vorgang abgeschlossen: {output_dir}")

    finally:
        parser.close()

def main():
    parser = argparse.ArgumentParser(description="SC / XFL Asset Renderer v3.3")
    parser.add_argument("--input", "-i", required=True, help="Pfad zur .fla Datei, .zip Datei oder entpacktem Ordner")
    parser.add_argument("--output", "-o", required=True, help="Zielordner")
    parser.add_argument("--fps", type=int, default=30, help="FPS für Animationen (Standard: 30)")
    parser.add_argument("--scale", type=float, default=1.0, help="Skalierungsfaktor (Standard: 1.0)")
    parser.add_argument("--limit", "-n", type=int, default=None, help="Max. Anzahl an zu rendernden Assets")
    parser.add_argument("--export-frames", action="store_true", help="Aktiviert den Export einzelner PNG-Frames pro Animation")
    parser.add_argument("--export-js", action="store_true", help="Generiert den HTML5 Canvas JS Real-Time Player & JSON Animationsdaten")
    parser.add_argument("--format", nargs="+", default=["png", "gif", "apng"], choices=["png", "gif", "apng", "frames"])

    args = parser.parse_args()
    render_project(
        args.input,
        args.output,
        fps=args.fps,
        scale=args.scale,
        formats=args.format,
        limit=args.limit,
        export_frames=args.export_frames,
        export_js=args.export_js
    )

if __name__ == "__main__":
    main()

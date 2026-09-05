# Foxhole Dynamic Vanilla + Complete Map Mod Builder

This version combines the original image builder with the dynamically discovered
World Conquest layout from the main game PAK.

## What it builds

For **vanilla** (from `War-WindowsNoEditor.pak`) and for **each complete map mod PAK**:

```text
output/<variant>/
├─ foxhole_map_2560x1554.png
├─ foxhole_map_5120x3108.png          # or native stitched resolution if native is smaller
├─ openlayers.json
├─ world_layout.json
├─ build_manifest.json
├─ individual_hex_img/
│  ├─ MapAcrithiaHex.png              # native-resolution source texture
│  ├─ ...
│  ├─ MapWrestaHex.png
│  └─ manifest.json
└─ tiles/
   ├─ foxhole_map_LU_2560x1554.png
   ├─ foxhole_map_RU_2560x1554.png
   ├─ foxhole_map_LD_2560x1554.png
   ├─ foxhole_map_RD_2560x1554.png
   └─ openlayers.json
```

With the current game assets (`2048x1776` per hex):

- base map: **2560x1554**;
- effective base hex size: **256x222**;
- high-resolution map: **5120x3108**;
- effective high-resolution hex size: **512x444**;
- each high-resolution quadrant: **2560x1554**;
- every individual hex PNG: **2048x1776 native resolution**.

The 2560 map and 5120 map are rendered directly from the native individual
hex textures; the base map is not made by repeatedly downscaling another
stitched image.

## Dynamic layout

The hard-coded `FOXHOLE_LAYOUT` dictionary is gone.

The program reads the current layout from the main PAK:

```text
War/Content/Blueprints/Data/BPMapList.uasset
```

and uses every record with:

```text
bIsInHexGrid = True
```

The `Image` property identifies the processed hex texture and `GridCoord`
provides its current world-grid position.

Therefore, when Siege Camp changes the World Conquest layout, the builder uses
the updated layout from the current main PAK.

## Configuration

Edit only:

```text
settings.txt
```

### Main PAK

```python
path_to_main_pak = r"D:\games\steamapps\common\Foxhole\War\Content\Paks\War-WindowsNoEditor.pak"
```

If it is empty:

```python
path_to_main_pak = r""
```

the program looks in its own directory for exactly:

```text
War-WindowsNoEditor.pak
```

### Map mods

```python
list_paths_to_mod_paks = [
    r"D:\FoxholeMods\War-WindowsNoEditor_Knights_MapModOfScience_v1_3_NoStyles_DarkRdz.pak",
    r"D:\FoxholeMods\AnotherCompleteMapMod.pak",
]
```

If the list is empty:

```python
list_paths_to_mod_paks = []
```

the program scans its own directory for `*.pak` files. A file named exactly
`War-WindowsNoEditor.pak` is the main PAK and is never treated as a mod.

## Complete mods only

There is **no vanilla fallback** for a partial mod.

Suppose the main `BPMapList` currently says there are 53 World Conquest regions.
A mod must contain all 53 corresponding processed `Map...Hex.uasset` images.

- 53/53 -> build the mod.
- 52/53 -> skip the mod.
- unrelated/unreadable PAK -> skip the PAK.

If the game later has a different number of `bIsInHexGrid` regions, completeness
is checked against that current number rather than a hard-coded 53.

## OpenLayers JSON

`openlayers.json` contains:

- FHS world extent;
- base image pixel size and extent;
- high-resolution image pixel size and extent;
- the four quadrant file names;
- each quadrant's pixel crop and FHS/OpenLayers extent.

Current world extent:

```text
[0.0, -205.7, 256.0, -50.3]
```

and the four tile extents are split at `(128, -128)`.

## Running

Install Pillow once if needed:

```text
py -3 -m pip install -r requirements.txt
```

Then simply double-click:

```text
RUN.bat
```

All PAK files are opened read-only. Generated files go under `output/`.
